# Test suite

Regression tests for the RetailOps-AI application.

## Running

From the repository root, install the development dependencies:

```bash
pip install -r src/requirements-dev.txt
```

Then run the desired test command:

```bash
pytest -v                 # full suite
pytest -v -m integration  # FastAPI end-to-end and PostgreSQL guard tests
pytest -v -m "not slow"   # skip the timeout tests
pytest --cov=src --cov-report=term-missing
```

PostgreSQL-backed tests require the internal PostgreSQL service; see the root
[Getting Started](../README.md#getting-started) instructions.

## Layout

| File                        | Scope                                                                 |
| --------------------------- | --------------------------------------------------------------------- |
| `conftest.py`               | Shared fixtures: sample SQLite DB, managers, LLM stub, internal store |
| `test_query_validator.py`   | Read-only enforcement, blocklists, injection/parsing edge cases        |
| `test_query_executor.py`    | Execution, truncation, timeouts, error handling, read-only guard       |
| `test_query_security.py`    | Read-only guards per backend (SQLite/PostgreSQL real, others emulated) |
| `test_schema_inspector.py`  | Table listing, columns, keys, relationships, `TableNotFoundError`      |
| `test_sql_tools.py`         | Agent facing tools and their failure artifacts                         |
| `test_sql_agent_prompt.py`  | Runtime substitution of dialect and row-limit prompt values            |
| `test_analysis_service.py`  | Agent flow, schema-only answers, `no_data`, self-correction, artefacts |
| `test_llm_factory.py`       | OpenAI/Gemini configuration and configuration errors                   |
| `test_database_connection.py` | URL validation, engine lifecycle, connection verification           |
| `test_pydantic_schemas.py`  | Response/request contract of the pydantic models                       |
| `test_api_integration.py`   | Full FastAPI workflow over `httpx.AsyncClient`                         |

## Rules

* Database-facing tests use the real SQL validator, query executor and schema
  inspector. SQLite tests use isolated databases; file-backed fixtures live
  under pytest's `tmp_path`.
* Agent-flow tests replace the LLM provider with `ScriptedChatModel` from
  `conftest.py`; trace-parsing tests use a stub agent, and the prompt test
  captures agent construction to verify rendered values.
* MySQL/MariaDB/SQL Server are not available locally, so their read-only
  guards are exercised with a recording stand-in for the *connection* only;
  the guard implementation itself always runs for real.  The PostgreSQL guard
  is tested against the real server.

## Internal store

The application-owned test database uses `retailops_test_<pid>` by default.
`RETAILOPS_TEST_DB` overrides that name; set it only to a dedicated, disposable
database, because the API-test fixtures clear its application tables and drop
it at session end. Do not point it at a developer database. Concurrent test
runs must not share the same overridden name. If PostgreSQL is unavailable,
the PostgreSQL-backed API and guard tests are skipped.
