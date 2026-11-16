"""Shared pytest fixtures for the RetailOps-AI regression suite.

Design rules enforced here:

* The SQL validator, query executor, schema inspector and the SQLite
  database under analysis are **never** mocked.  They are the system
  under test.
* Only the LLM / agent provider is replaced by a deterministic stub
  (:class:`ScriptedChatModel`).
* Every fixture that touches a database is function scoped so tests stay
  isolated from each other.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Sequence

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

# --------------------------------------------------------------------------
# Import path / environment bootstrap (must happen before app imports)
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# The application keeps its own conversation history in PostgreSQL.  Tests
# must never touch a developer database, therefore the internal store is
# redirected to a dedicated test database *before* the cached settings
# singleton is created.
#
# The database name carries the process id so that two test runs on the same
# machine (for example an IDE run next to a terminal run) cannot truncate
# each other's data.  It is dropped again when the session ends.
INTERNAL_TEST_DB = os.environ.get("RETAILOPS_TEST_DB") or (
    f"retailops_test_{os.getpid()}"
)
os.environ["POSTGRES_MAIN_DATABASE"] = INTERNAL_TEST_DB

from agents.llm.llm_factory import LLMFactory  # noqa: E402
from database.connection import DatabaseConnectionManager  # noqa: E402
from database.query_executor import QueryExecutor  # noqa: E402
from database.schema_inspector import SchemaInspector  # noqa: E402

# --------------------------------------------------------------------------
# Sample external database
# --------------------------------------------------------------------------
SAMPLE_SCHEMA = """
CREATE TABLE customers (
    id          INTEGER PRIMARY KEY NOT NULL,
    name        TEXT    NOT NULL,
    email       TEXT,
    city        TEXT,
    signup_date TEXT    NOT NULL
);

CREATE TABLE orders (
    id          INTEGER PRIMARY KEY NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date  TEXT    NOT NULL,
    status      TEXT    NOT NULL,
    total       REAL    NOT NULL
);

CREATE TABLE order_items (
    id         INTEGER PRIMARY KEY NOT NULL,
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    product    TEXT    NOT NULL,
    quantity   INTEGER NOT NULL,
    unit_price REAL    NOT NULL
);
"""

SAMPLE_SEED = [
    "INSERT INTO customers VALUES "
    "(1, 'Alice', 'alice@example.com', 'Berlin', '2024-01-05'),"
    "(2, 'Bob', 'bob@example.com', 'Lisbon', '2024-02-11'),"
    "(3, 'Carla', NULL, 'Berlin', '2024-03-02'),"
    "(4, 'Dan', 'dan@example.com', 'Oslo', '2024-05-19')",
    "INSERT INTO orders VALUES "
    "(1, 1, '2024-06-01', 'paid', 120.50),"
    "(2, 1, '2024-06-04', 'paid', 45.00),"
    "(3, 2, '2024-06-07', 'shipped', 210.75),"
    "(4, 3, '2024-06-11', 'cancelled', 15.25),"
    "(5, 4, '2024-06-15', 'paid', 89.99)",
    "INSERT INTO order_items VALUES "
    "(1, 1, 'Keyboard', 1, 80.00),"
    "(2, 1, 'Mouse', 2, 20.25),"
    "(3, 2, 'Cable', 1, 45.00),"
    "(4, 3, 'Monitor', 1, 210.75),"
    "(5, 4, 'Sticker', 1, 15.25),"
    "(6, 5, 'Desk lamp', 1, 89.99)",
]


def build_sample_database(path: Path) -> Path:
    """Create a realistic SQLite database with PKs, FKs and seed data."""
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SAMPLE_SCHEMA)
        for statement in SAMPLE_SEED:
            connection.execute(statement)
        connection.commit()
    finally:
        connection.close()
    return path


# --------------------------------------------------------------------------
# Deterministic LLM stub (the only mocked component in the suite)
# --------------------------------------------------------------------------
class ScriptedChatModel(BaseChatModel):
    """A chat model that replays a fixed list of AI messages.

    Every model call is recorded in :attr:`calls` so tests can assert on
    what the agent actually sent to the model.
    """

    responses: list[AIMessage] = []
    unique_tool_call_ids: bool = False
    _index: int = PrivateAttr(default=0)
    _calls: list[list[BaseMessage]] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-chat-model"

    @property
    def calls(self) -> list[list[BaseMessage]]:
        """Recorded prompts, one entry per model invocation."""
        return self._calls

    def _generate(  # type: ignore[override]
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._calls.append(list(messages))

        if not self.responses:
            raise AssertionError(
                "ScriptedChatModel was invoked but no responses were configured."
            )

        index = min(self._index, len(self.responses) - 1)
        self._index += 1

        message = self.responses[index]

        if self.unique_tool_call_ids and message.tool_calls:
            # Repeated tool calls need distinct ids, otherwise the agent
            # state collapses the duplicated tool results.
            message = AIMessage(
                content=message.content,
                tool_calls=[
                    {**call, "id": f"{call['id']}_{index}"}
                    for call in message.tool_calls
                ],
            )

        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":
        """Tool calling is supported; the script already contains the calls."""
        return self


class FakeLLMProvider:
    """Hands out scripted chat models, one per agent instantiation."""

    def __init__(self) -> None:
        self.scripts: list[list[AIMessage]] = []
        self.models: list[ScriptedChatModel] = []
        self.unique_tool_call_ids = False

    def install(self, *scripts: list[AIMessage]) -> "FakeLLMProvider":
        self.scripts = [list(script) for script in scripts]
        return self

    def install_with_unique_tool_call_ids(
        self, *scripts: list[AIMessage]
    ) -> "FakeLLMProvider":
        """Install scripts whose tool calls get a fresh id on every turn."""
        self.scripts = [list(script) for script in scripts]
        self.unique_tool_call_ids = True
        return self

    def create(self) -> ScriptedChatModel:
        if not self.scripts:
            raise AssertionError("No LLM script was installed for this test.")

        script = self.scripts[min(len(self.models), len(self.scripts) - 1)]
        unique_tool_call_ids = self.unique_tool_call_ids
        model = ScriptedChatModel(
            responses=script, unique_tool_call_ids=unique_tool_call_ids
        )
        self.models.append(model)
        return model


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> FakeLLMProvider:
    """Replaces the LLM provider with a deterministic scripted model.

    The SQL agent, its tools, the validator, the executor and the real
    SQLite database keep running for real.
    """
    provider = FakeLLMProvider()

    def _create(self: LLMFactory, *args: Any, **kwargs: Any) -> ScriptedChatModel:
        return provider.create()

    monkeypatch.setattr(LLMFactory, "create", _create)
    return provider


@pytest.fixture
def sample_db_path(tmp_path: Path) -> str:
    """Path of a freshly built SQLite database (rebuilt for every test)."""
    path = build_sample_database(tmp_path / "external.db")
    return path.as_posix()


@pytest.fixture
def db_manager(sample_db_path: str):
    """A connection manager bound to the temporary sample database."""
    manager = DatabaseConnectionManager(f"sqlite:///{sample_db_path}")
    try:
        yield manager
    finally:
        manager.close()


@pytest.fixture
def schema_inspector(db_manager: DatabaseConnectionManager) -> SchemaInspector:
    return SchemaInspector(db_manager.engine)


@pytest.fixture
def query_executor(db_manager: DatabaseConnectionManager) -> QueryExecutor:
    return QueryExecutor(db_manager, max_rows=100, timeout_seconds=5)


# --------------------------------------------------------------------------
# Internal (application owned) PostgreSQL store - used by the API tests
# --------------------------------------------------------------------------
def _ensure_internal_database() -> None:
    """Create the dedicated test database if it does not exist yet."""
    import asyncpg

    from core.config import get_settings

    settings = get_settings()

    async def _create() -> None:
        connection = await asyncpg.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USERNAME,
            password=settings.POSTGRES_PASSWORD,
            database="postgres",
        )
        try:
            exists = await connection.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", INTERNAL_TEST_DB
            )
            if not exists:
                await connection.execute(f'CREATE DATABASE "{INTERNAL_TEST_DB}"')
        finally:
            await connection.close()

    asyncio.run(_create())


@pytest.fixture(scope="session")
def internal_database() -> str:
    """Make sure the dedicated internal test database exists."""
    try:
        _ensure_internal_database()
    except Exception as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"Internal PostgreSQL test database is unavailable: {exc}")
    return INTERNAL_TEST_DB


@pytest.fixture(scope="session")
def internal_store(internal_database: str) -> None:
    """Create the application schema inside the internal test database."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from core.config import get_settings
    from models.db_schemas import SQLAlchemyBase

    settings = get_settings()

    url = (
        f"postgresql+asyncpg://{settings.POSTGRES_USERNAME}:"
        f"{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:"
        f"{settings.POSTGRES_PORT}/{internal_database}"
    )

    async def _create() -> None:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(SQLAlchemyBase.metadata.create_all)
        finally:
            await engine.dispose()

    asyncio.run(_create())

    yield

    async def _cleanup() -> None:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "TRUNCATE TABLE message, conversation, connection_record CASCADE"
                    )
                )
        finally:
            await engine.dispose()

    asyncio.run(_cleanup())

    # The database only exists for this test run, so it is removed again.
    # Failures here must not fail the test session.
    try:
        asyncio.run(_drop_internal_database(internal_database))
    except Exception:  # pragma: no cover - depends on the environment
        pass


def _drop_internal_database(database: str) -> None:
    """Drop the dedicated test database and close its remaining sessions."""
    import asyncpg

    from core.config import get_settings

    settings = get_settings()

    async def _drop() -> None:
        connection = await asyncpg.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USERNAME,
            password=settings.POSTGRES_PASSWORD,
            database="postgres",
        )
        try:
            await connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid()",
                database,
            )
            await connection.execute(f'DROP DATABASE IF EXISTS "{database}"')
        finally:
            await connection.close()

    asyncio.run(_drop())

