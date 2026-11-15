# RetailOps AI

RetailOps AI is a FastAPI application that lets you ask questions about a connected database in natural language. It generates and runs SQL to answer questions, and saves conversations so you can ask follow-up questions.

## Features

- Connect to an external database for analysis.
- Ask questions in natural language and receive answers based on database data.
- Continue a conversation with follow-up questions.
- Browse and delete saved conversations and their message history.
- View the API through Swagger UI or Scalar.

## Getting Started

Run the following commands from the repository root.

### 1. Configure the environment

Create the application and database environment files:

```bash
cp .env.example .env
cp docker/.env.example docker/.env
```

Set the language model provider and its credentials in `.env`. The PostgreSQL username, password, and database name in `.env` must match the values in `docker/.env`.

### 2. Start the internal database

The internal PostgreSQL database stores connection records and conversation history. The database is available on port `5433` on your machine.

```bash
cd docker
docker compose up -d
cd ..
```

### 3. Install dependencies

```bash
cd src
pip install -r requirements.txt
cd ..
```

### 4. Apply database migrations

Configure Alembic and create the internal database schema:

```bash
cd src/models/db_schemas/Retailops
cp alembic.ini.example alembic.ini
```

Update `sqlalchemy.url` in `alembic.ini` with the internal PostgreSQL credentials, then apply the migrations:

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

## API Documentation

With the application running, open:

- Swagger UI: <http://localhost:5000/docs>
- Scalar API reference: <http://localhost:5000/scalar>

The API base URL is `http://localhost:5000`.

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

The response includes the connection status, database dialect, and a `connection_id`.

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

An analysis request requires an active database connection. Requests without one return `409 Conflict`.

### Manage conversations and connections

- `GET /api/v1/conversations` — List saved conversations; optionally filter by `connection_id`.
- `GET /api/v1/conversations/{conversation_id}` — Retrieve a conversation and its message history.
- `DELETE /api/v1/conversations/{conversation_id}` — Delete a conversation and its messages.
- `DELETE /api/v1/connections` — Close the active database connection.
