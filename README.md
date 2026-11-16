# RetailOps AI

RetailOps AI is a FastAPI service that lets you ask questions about a connected database in natural language. It inspects the schema, generates read-only SQL, executes it, and answers with the resulting data. Every turn is stored, so you can ask follow-up questions in the same conversation.

## Table of Contents

- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
  - [Directory Structure](#directory-structure)
  - [Request Lifecycle](#request-lifecycle)
  - [The SQL Agent](#the-sql-agent)
  - [Read-Only Safety](#read-only-safety)
  - [Internal Data Model](#internal-data-model)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Using the API](#using-the-api)
- [Testing](#testing)
- [Continuous Integration](#continuous-integration)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Key Features

- Connect to an external database (SQLite, PostgreSQL, MySQL/MariaDB, SQL Server) and analyse it.
- Ask questions in natural language; the agent inspects the schema before writing SQL.
- Continue a conversation with follow-up questions - prior turns are fed back as context.
- Browse and delete saved conversations and their message history.
- Inspect the connected schema directly through the API (`/api/v1/schema`).
- Generated SQL is validated as read-only before it reaches the database.
- Swagger UI and Scalar API reference out of the box.

## Tech Stack

- **Language**: Python 3.14 (CI runs 3.14; the code targets 3.11+ syntax)
- **Web framework**: FastAPI 0.162.0 with Uvicorn 0.54.0
- **API reference**: Swagger UI (built in) and Scalar 1.9.1
- **Data validation / settings**: Pydantic 2.14.1, pydantic-settings 2.16.2
- **ORM**: SQLAlchemy 2.0.52 - async (asyncpg) for the internal store, sync engines for the analysed database
- **SQL parsing**: sqlglot 30.27.0 (read-only enforcement and dialect-aware rewriting)
- **Agent framework**: LangChain 1.4.7 / langchain-core 1.7.3 (`create_agent` on LangGraph)
- **Model providers**: OpenAI (`langchain-openai`) or Google Gemini (`langchain-google-genai`)
- **Internal database**: PostgreSQL (via Docker Compose) with Alembic 1.20.1 migrations
- **Database drivers**: `psycopg2-binary`, `PyMySQL`, `pyodbc`, `asyncpg`
- **Tests**: pytest 9.2.0, pytest-asyncio, pytest-cov, httpx
- **CI**: GitHub Actions (`.github/workflows/ci.yml`)

## Architecture

### Directory Structure

```
src/
├── main.py                     # FastAPI app, lifespan (engine + connection state), router registration
├── core/
│   └── config.py               # Pydantic Settings; every environment variable lives here
├── agents/
│   ├── sql_agent.py            # LangChain agent: model + tools + system prompt
│   ├── llm/llm_factory.py      # Builds the chat model from GENERATION_BACKEND / MODEL_ID / keys
│   ├── prompts/                # System prompt for the analyst agent
│   └── tools/sql_tools.py      # Agent-facing tools: list_tables, describe_table, execute_sql_query
├── controllers/
│   └── analysis_controller.py  # Thin wrapper around AnalysisService
├── services/
│   └── analysis_service.py     # Runs the agent and turns the tool trace into an AnalysisResponse
├── database/
│   ├── connection.py           # DatabaseConnectionManager: URL parsing, engine lifecycle, test connection
│   ├── query_validator.py      # sqlglot AST check: single read-only SELECT statement
│   ├── query_security.py       # Per-backend read-only transaction + statement timeout
│   ├── query_executor.py       # Executes the validated SQL, caps rows, reports truncation
│   ├── schema_inspector.py     # Table listing, columns, primary/foreign keys
│   └── repositories/           # ConversationRepository, ConnectionRepository (internal store)
├── models/
│   ├── db_schemas/             # SQLAlchemy models for the internal PostgreSQL store
│   │   └── Retailops/          #   schemes/ + alembic/ migrations
│   ├── pydantic_schemas/       # Request/response contracts
│   └── enums/chat_enums.py     # MessageRole, MessageStatus
└── routes/
    ├── base.py                 # GET /api/v1/ (health check)
    ├── connections.py          # Connect / status / disconnect
    ├── schema.py               # Schema inspection endpoints
    ├── analysis.py             # POST /api/v1/analysis
    ├── conversations.py        # Conversation history endpoints
    └── dependencies.py         # get_db_manager, get_internal_db

docker/                         # PostgreSQL container for the internal store
tests/                          # pytest regression suite
```

### Request Lifecycle

1. The client calls an endpoint; `get_db_manager` / `get_internal_db` resolve the active external connection and the internal database session.
2. The route validates the payload (Pydantic) and delegates to a controller or service.
3. `AnalysisController` calls `AnalysisService.analyze()`, which runs the LangChain agent in a thread pool.
4. The agent calls `list_tables` / `describe_table` (via `SchemaInspector`) and `execute_sql_query` (via `QueryExecutor`).
5. `QueryValidator` parses the SQL with sqlglot and rejects anything that is not a single read-only `SELECT`; `query_security` wraps the execution in a read-only transaction with a statement timeout.
6. The tool artefacts are collected into an `AnalysisResponse` (`success`, `no_data` or `failed`).
7. The route persists the turn (question + answer, queries, schema results, metadata) in the internal PostgreSQL store and returns the response.

### The SQL Agent

The agent is created per request from the connected database:

- **Model**: chosen by `LLMFactory` from `GENERATION_BACKEND` (`OPENAI` or `GEMINI`) and `MODEL_ID`.
- **Tools**:
  - `list_tables` - table names of the connected database (optionally scoped to a schema).
  - `describe_table` - columns, types, nullability, primary key and foreign keys of a table.
  - `execute_sql_query` - validated, read-only `SELECT` execution with a row cap.
- **System prompt**: instructs the model to inspect the schema before writing SQL, to select only needed columns, to retry failed queries with verified schema information, and to treat database content as data rather than instructions.
- **History**: the last `CHAT_HISTORY_LIMIT` user/assistant messages of the conversation are replayed to the model, with the executed SQL appended to assistant turns.
- **Limits**: `AGENT_RECURSION_LIMIT` caps the agent graph; exceeding it is reported as a failed analysis.

### Read-Only Safety

Three layers protect the analysed database:

1. **AST validation** (`query_validator.py`) - the query is parsed with sqlglot and must be exactly one statement whose root is `SELECT` / `UNION` / `INTERSECT` / `EXCEPT`. DML and DDL nodes are rejected, dangerous functions (`pg_sleep`, `xp_cmdshell`, `load_file`, ...) are blocked, MySQL executable comments and variable assignments are refused, and the SQL that is executed is regenerated from the inspected AST.
2. **Execution guard** (`query_security.py`) - the statement runs inside a read-only transaction with a statement timeout: `SET TRANSACTION READ ONLY` + `statement_timeout` on PostgreSQL, `PRAGMA query_only` + a progress handler on SQLite, `max_execution_time` on MySQL/MariaDB and a driver timeout on SQL Server.
3. **Result limits** (`query_executor.py`) - at most `SQL_MAX_ROWS` rows are returned; larger result sets are counted and flagged with `truncated: true`.

### Internal Data Model

The application owns a PostgreSQL database (`POSTGRES_MAIN_DATABASE`) that stores connections and conversation history. Migrations live in `src/models/db_schemas/Retailops/alembic/versions/`.

```
connection_record
├── id              UUID  PK
├── fingerprint     VARCHAR(255)  unique  (sha256 of the password-free URL)
├── dialect         VARCHAR(50)
├── safe_url        VARCHAR(500)  (password hidden)
├── database_name   VARCHAR(100)
├── created_at      TIMESTAMPTZ
└── last_connected_at TIMESTAMPTZ

conversation
├── id           UUID  PK
├── connection_id UUID  FK → connection_record.id (ON DELETE CASCADE)
├── title        VARCHAR(255)   (the first question, truncated)
├── created_at   TIMESTAMPTZ
└── updated_at   TIMESTAMPTZ

message
├── id              UUID  PK
├── conversation_id UUID  FK → conversation.id (ON DELETE CASCADE)
├── role            VARCHAR(50)   ('user' | 'assistant')
├── content         TEXT
├── status          VARCHAR(50)   ('success' | 'no_data' | 'failed')
├── queries         JSONB         (SQL execution results)
├── schema_results  JSONB         (schema inspection results)
├── metadata_json   JSONB         (dialect, tools used)
├── error           TEXT
└── created_at      TIMESTAMPTZ
```

## Prerequisites

- Python 3.11 or newer (CI uses 3.14)
- Docker and Docker Compose (for the internal PostgreSQL store)
- An OpenAI API key **or** a Google Gemini API key
- A database you want to analyse, with credentials you are allowed to read

## Getting Started

All commands are run from the repository root.

### 1. Configure the environment

Create the application and database environment files:

```bash
cp .env.example .env
cp docker/.env.example docker/.env
```

In `.env` set the language model provider and its credentials:

| Backend   | Variables                                                        |
| --------- | ---------------------------------------------------------------- |
| `OPENAI`  | `GENERATION_BACKEND="OPENAI"`, `OPENAI_API_KEY`, `MODEL_ID`       |
| `GEMINI`  | `GENERATION_BACKEND="GEMINI"`, `GOOGLE_API_KEY`, `MODEL_ID`       |

### 2. Start the internal database

The internal PostgreSQL database stores connection records and conversation history. The container is published on port `5433` on your machine.

```bash
cd docker
docker compose up -d
cd ..
```

Check that it is healthy:

```bash
docker compose -f docker/docker-compose.yml ps
```

### 3. Install dependencies

```bash
cd src
pip install -r requirements.txt
cd ..
```

For development (tests and coverage):

```bash
pip install -r src/requirements-dev.txt
```

### 4. Apply database migrations

Alembic is configured per project; copy the example configuration and point it at the internal database:

```bash
cd src/models/db_schemas/Retailops
cp alembic.ini.example alembic.ini
```

Update `sqlalchemy.url` in `alembic.ini` with the internal PostgreSQL credentials, for example:

```ini
sqlalchemy.url = postgresql://postgres:password123@localhost:5433/RetailOps
```

Then apply the migrations:

```bash
alembic upgrade head
cd ../../../..
```

For more information about Alembic configuration and migrations, see the [Alembic guide](src/models/db_schemas/Retailops/README.md).

### 5. Start the application

```bash
cd src
uvicorn main:app --reload --host 0.0.0.0 --port 5000
```

You should see:

```text
INFO:     Uvicorn running on http://0.0.0.0:5000
INFO:     Application startup complete.
```

## Configuration

All configuration lives in `src/core/config.py` and is read from the repository `.env` file.

The most important settings:

| Setting                | Purpose                                                                 |
| ---------------------- | ----------------------------------------------------------------------- |
| `GENERATION_BACKEND`   | `OPENAI` or `GEMINI` - selects the model provider.                      |
| `MODEL_ID`             | Model identifier passed to the provider (required).                      |
| `SQL_MAX_ROWS`         | Maximum number of rows returned by a single query (default `100`).       |
| `SQL_TIMEOUT_SECONDS`  | Per-query execution timeout (default `5.0`).                            |
| `CHAT_HISTORY_LIMIT`   | Number of past messages replayed to the agent (default `10`). |
| `AGENT_RECURSION_LIMIT`| Maximum agent graph steps (default `25`).                               |
| `POSTGRES_*`           | Connection details of the internal PostgreSQL store.                    |

## Environment Variables

| Variable                | Required | Default | Description                                              |
| ----------------------- | -------- | ------- | -------------------------------------------------------- |
| `APP_NAME`              | yes      | -       | Application name shown by the health check.              |
| `APP_VERSION`           | yes      | -       | Application version shown by the health check.           |
| `CORS_ORIGINS`          | no       | `*`     | Comma-separated list of allowed origins.                 |
| `POOL_PRE_PING`         | yes      | -       | Enable connection pool pre-ping on the analysed engine. |
| `CONNECT_TIMEOUT`       | yes      | -       | Connection timeout in seconds for the analysed database. |
| `SQL_MAX_ROWS`          | no       | `100`   | Maximum rows returned per query.                         |
| `SQL_TIMEOUT_SECONDS`   | no       | `5.0`   | Query execution timeout in seconds.                      |
| `CHAT_HISTORY_LIMIT`    | no       | `10`    | Past messages replayed to the agent.          |
| `POSTGRES_USERNAME`     | yes      | -       | Internal store user.                                     |
| `POSTGRES_PASSWORD`     | yes      | -       | Internal store password.                                 |
| `POSTGRES_HOST`         | yes      | -       | Internal store host (`localhost` with Docker Compose).   |
| `POSTGRES_PORT`         | yes      | -       | Internal store port (`5433` with Docker Compose).        |
| `POSTGRES_MAIN_DATABASE`| yes      | -       | Internal store database name.                            |
| `GENERATION_BACKEND`    | no       | `OPENAI`| `OPENAI` or `GEMINI`.                                    |
| `OPENAI_API_KEY`        | if OPENAI| -       | OpenAI API key.                                          |
| `OPENAI_API_URL`        | no       | -       | Custom OpenAI-compatible base URL.                      |
| `GOOGLE_API_KEY`        | if GEMINI| -       | Google Gemini API key.                                   |
| `MODEL_ID`              | yes      | -       | Model identifier, e.g. `gpt-4o-mini` or `gemini-2.0-flash`. |
| `DEFAULT_MAX_TOKENS`    | no       | provider| Maximum tokens per completion.                          |
| `DEFAULT_TEMPERATURE`   | no       | `0.0`   | Sampling temperature (0.0 - 2.0).                       |
| `LLM_TIMEOUT`           | no       | `60.0`  | Model request timeout in seconds.                        |
| `AGENT_RECURSION_LIMIT` | no       | `25`    | Maximum agent graph steps.                               |

Secrets are declared as `SecretStr` and are never written to the log; connection URLs are stored password-free.

## API Reference

With the application running, open:

- Swagger UI: <http://localhost:5000/docs>
- Scalar API reference: <http://localhost:5000/scalar>

The API base URL is `http://localhost:5000`.

| Method   | Path                                          | Description                                                   |
| -------- | --------------------------------------------- | ------------------------------------------------------------- |
| `GET`    | `/api/v1/`                                    | Health check; returns the app name and version.               |
| `GET`    | `/api/v1/connections`                         | Status of the active database connection.                     |
| `POST`   | `/api/v1/connections`                         | Connect to a database to analyse (`201`).                     |
| `DELETE` | `/api/v1/connections`                         | Close the active connection (`204`).                          |
| `GET`    | `/api/v1/schema/tables`                       | List tables of the connected database.                         |
| `GET`    | `/api/v1/schema/tables/{table_name}`          | Columns, primary key and foreign keys of one table.            |
| `POST`   | `/api/v1/analysis`                            | Ask a question; returns the answer and the executed SQL.      |
| `GET`    | `/api/v1/conversations`                       | List conversations, optionally filtered by `connection_id`.    |
| `GET`    | `/api/v1/conversations/{conversation_id}`      | One conversation including its message history.                |
| `DELETE` | `/api/v1/conversations/{conversation_id}`      | Delete a conversation and its messages (`204`).               |

Status codes used by the API:

| Code  | Meaning                                                                        |
| ----- | ------------------------------------------------------------------------------ |
| `200` | Request succeeded.                                                              |
| `201` | A database connection was created.                                              |
| `204` | A connection or conversation was deleted.                                       |
| `400` | The supplied database URL could not be connected to.                           |
| `404` | The conversation does not exist (or belongs to another connection).            |
| `409` | No active connection, a connection already exists, or one is being deleted.    |
| `500` | The analysis failed or the internal store could not be reached.                |

## Using the API

### Connect to a database

Connect to the database you want to analyze:

```http
POST /api/v1/connections
Content-Type: application/json

{
  "database_url": "postgresql://user:password@localhost:5432/database"
}
```

The response includes the connection status, database dialect, and a `connection_id`. Only one connection can be active at a time.

### Inspect the schema

```http
GET /api/v1/schema/tables
```

```http
GET /api/v1/schema/tables/orders
```

### Ask a question

```http
POST /api/v1/analysis
Content-Type: application/json

{
  "question": "How many orders were placed?"
}
```

The response includes the answer, analysis status, executed queries, schema results, metadata, and a `conversation_id`. Include that ID in later requests to ask follow-up questions in the same conversation:

```http
POST /api/v1/analysis
Content-Type: application/json

{
  "question": "How many of those orders were delivered?",
  "conversation_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
}
```

An analysis request requires an active database connection. Requests without one return `409 Conflict`. A `conversation_id` that does not belong to the active connection returns `404 Not Found`.

A completed analysis returns `200 OK`. The `status` field of the response tells the outcome apart:

| `status`  | HTTP status | Meaning                                               |
| --------- | ----------- | ----------------------------------------------------- |
| `success` | `200 OK`    | The question was answered from the database.          |
| `no_data` | `200 OK`    | The query ran but matched no rows.                    |
| `failed`  | `500`       | The analysis could not be completed; `error` says why.|

A failed analysis is still persisted, so the turn shows up in the conversation history and can be used as context for the next question.

### Manage conversations and connections

- `GET /api/v1/connections` — Check the active database connection status.
- `GET /api/v1/conversations` — List saved conversations; optionally filter by `connection_id`.
- `GET /api/v1/conversations/{conversation_id}` — Retrieve a conversation and its message history.
- `DELETE /api/v1/conversations/{conversation_id}` — Delete a conversation and its messages.
- `DELETE /api/v1/connections` — Close the active database connection.

## Testing

The regression suite lives in `tests/` and is described in detail in [tests/README.md](tests/README.md). The SQL validator, executor, schema inspector and the SQLite database under analysis are never mocked — only the LLM provider is replaced by a deterministic scripted model.

Install the development dependencies and run the suite:

```bash
pip install -r src/requirements-dev.txt

pytest -v                        # full suite
pytest -v -m integration         # FastAPI end-to-end and PostgreSQL guard tests
pytest -v -m "not slow"          # skip the timeout tests
pytest --cov=src --cov-report=term-missing
```

The configuration lives in `pytest.ini` (`testpaths = tests`, `pythonpath = src`).

The API tests need the internal PostgreSQL store. It uses `retailops_test_<pid>` by default; `RETAILOPS_TEST_DB` overrides the name. Use that override only for a dedicated, disposable database: the API fixtures clear application tables and drop the database at session end. Do not point it at a developer database, and do not share an overridden name across concurrent test runs. PostgreSQL-backed API and guard tests are skipped if PostgreSQL is unreachable.

## Continuous Integration

`.github/workflows/ci.yml` runs on every push to `main` and on every pull request:

1. A `postgres:18-alpine` service container is started.
2. The application settings are provided as environment variables (the repository `.env` file is git-ignored).
3. Python 3.14 is set up and `src/requirements-dev.txt` is installed.
4. The suite is executed with `pytest -v`.

The LLM credentials in CI are dummy values: the provider is replaced by the scripted stub in `tests/conftest.py`, so no request leaves the runner.

## Troubleshooting

### The application fails to start with a settings error

**Error:** `ValidationError` for missing fields such as `APP_NAME` or `POSTGRES_USERNAME`.

**Solution:** `.env` was not created or is incomplete. Copy `.env.example` to `.env` and fill in every value. The file must be in the repository root - `config.py` reads `<repo>/.env`.

### Database connection refused

**Error:** `Unable to establish database connection. Check credentials and server availability.`

**Solution:**

1. Check that the internal database is running: `docker compose -f docker/docker-compose.yml ps`.
2. Verify the credentials in `.env` and `docker/.env` match (`POSTGRES_USERNAME`/`POSTGRES_USER`, `POSTGRES_PASSWORD`/`POSTGRES_PASSWORD`, `POSTGRES_MAIN_DATABASE`/`POSTGRES_DB`).
3. Verify the port: the container publishes `5433`, so `POSTGRES_PORT=5433`.

### Migrations have not been applied

**Error:** `relation "conversation" does not exist` when listing conversations.

**Solution:**

```bash
cd src/models/db_schemas/Retailops
alembic upgrade head
```

Make sure `sqlalchemy.url` in `alembic.ini` points at the same database as `POSTGRES_MAIN_DATABASE`.

### The analysed database cannot be reached

**Error:** `400 Bad Request` - "Unable to connect to database."

**Solution:**

1. Confirm the URL scheme and the installed driver: `postgresql+psycopg2://`, `mysql+pymysql://`, `mssql+pyodbc://` or `sqlite:///path/to/file.db`.
2. The URL is validated by SQLAlchemy; a malformed URL raises `DatabaseConnectionError` and is reported as `400`.
3. For SQL Server the `pyodbc` driver must be installed on the machine (`ODBC Driver 17/18 for SQL Server`).

### The agent cannot answer

**Error:** `status` is `failed` with `Agent exceeded the maximum recursion limit.`

**Solution:** raise `AGENT_RECURSION_LIMIT` in `.env`, or simplify the question. A failed query also returns `failed` with the SQL error in `error` - the executed SQL is available in `queries`.

### The model is not configured

**Error:** `LLMConfigurationError: MODEL_ID must be configured.` or `OPENAI_API_KEY is required.`

**Solution:** set `MODEL_ID` and the API key of the backend selected by `GENERATION_BACKEND` in `.env`.

### The answer contains no rows

**Error:** `status` is `no_data`.

**Solution:** the query executed successfully but matched nothing. `queries[].data.total_rows` holds the real number of matching rows, and `truncated` shows whether the returned rows were capped by `SQL_MAX_ROWS`.

## License

[MIT](LICENSE) - Copyright (c) 2026 Saleh Mohamed.
