"""Regression tests for the read-only guards (`database.query_security`).

The SQLite guard is exercised against a real SQLite database and the
PostgreSQL guard against the real PostgreSQL server that backs the
application.  MySQL/MariaDB/SQL Server are not available in the test
environment, so those backends are exercised with a small recording stand-in
for the *connection* only - the guard implementation under test is always the
real one.

The SQLite behaviour that is already covered by `test_query_executor.py`
(restore after a successful query, writes blocked inside the guard, invalid
timeout values, unsupported backend) is not repeated here.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from database.query_security import (
    QuerySecurityError,
    protected_query,
)


# --------------------------------------------------------------------------
# Stand-ins for servers that are not available locally
# --------------------------------------------------------------------------
class _Result:
    """Minimal result object exposing the `scalar_one()` API used by guards."""

    def __init__(self, value: Any = None) -> None:
        self._value = value

    def scalar_one(self) -> Any:
        return self._value


class RecordingConnection:
    """A connection double that records the statements a guard issues.

    It is used for the MySQL/MariaDB/SQL Server guards only.  Every guard
    statement is captured so the tests can assert on the real protocol the
    guard speaks (session timeouts, read-only transactions, driver timeouts).
    """

    def __init__(
        self,
        dialect_name: str,
        driver: str | None = None,
        is_mariadb: bool = False,
        values: dict[str, list[Any]] | None = None,
        raw: Any = None,
        fail_on: tuple[str, ...] = (),
    ) -> None:
        self.dialect = SimpleNamespace(
            name=dialect_name, driver=driver, is_mariadb=is_mariadb
        )
        self.executed: list[str] = []
        self.rolled_back = False
        self.invalidated = False
        self._values = values or {}
        self._raw = raw
        self._fail_on = fail_on

    @property
    def connection(self) -> SimpleNamespace:
        return SimpleNamespace(driver_connection=self._raw)

    def exec_driver_sql(self, sql: str) -> _Result:
        self.executed.append(sql)

        if sql in self._fail_on:
            raise SQLAlchemyError(f"simulated failure for {sql!r}")

        for key, values in self._values.items():
            if key in sql:
                value = values[0] if len(values) == 1 else values.pop(0)
                return _Result(value)

        return _Result(None)

    def rollback(self) -> None:
        self.rolled_back = True

    def invalidate(self) -> None:
        self.invalidated = True


# --------------------------------------------------------------------------
# MySQL / MariaDB
# --------------------------------------------------------------------------
def test_mysql_guard_uses_a_read_only_transaction_and_a_session_timeout():
    connection = RecordingConnection("mysql", values={"max_execution_time": [1000]})

    with protected_query(connection, "SELECT 1", 5) as safe_sql:
        assert safe_sql == "SELECT 1"
        assert "SET SESSION max_execution_time = 5000" in connection.executed
        assert "START TRANSACTION READ ONLY" in connection.executed

    assert "SET SESSION max_execution_time = 1000" in connection.executed
    assert connection.rolled_back is True


def test_mariadb_guard_wraps_the_statement_with_a_max_statement_time():
    connection = RecordingConnection("mysql", is_mariadb=True)

    with protected_query(connection, "SELECT 1", 2.5) as safe_sql:
        assert safe_sql == "SET STATEMENT max_statement_time=2.5 FOR SELECT 1"
        assert "START TRANSACTION READ ONLY" in connection.executed

    assert connection.rolled_back is True


def test_mariadb_guard_does_not_touch_the_session_timeout():
    connection = RecordingConnection("mysql", is_mariadb=True)

    with protected_query(connection, "SELECT 1", 5):
        pass

    assert not any("max_execution_time" in sql for sql in connection.executed)


def test_mysql_guard_invalidates_the_connection_when_restoring_fails():
    connection = RecordingConnection(
        "mysql",
        values={"max_execution_time": [1000]},
        fail_on=("SET SESSION max_execution_time = 1000",),
    )

    with pytest.raises(SQLAlchemyError, match="simulated failure"):
        with protected_query(connection, "SELECT 1", 5):
            pass

    assert connection.invalidated is True


# --------------------------------------------------------------------------
# SQL Server
# --------------------------------------------------------------------------
def test_mssql_guard_requires_the_pyodbc_driver():
    connection = RecordingConnection("mssql", driver="pymssql")

    with pytest.raises(QuerySecurityError, match="requires the pyodbc driver"):
        with protected_query(connection, "SELECT 1", 5):
            pass


def test_mssql_guard_sets_and_restores_the_driver_timeout():
    raw = SimpleNamespace(timeout=0)
    connection = RecordingConnection("mssql", driver="pyodbc", raw=raw)

    with protected_query(connection, "SELECT 1", 5) as safe_sql:
        assert safe_sql == "SELECT 1"
        assert raw.timeout == 5

    assert raw.timeout == 0
    assert connection.rolled_back is True


def test_mssql_guard_invalidates_the_connection_when_restoring_fails():
    raw = SimpleNamespace(timeout=0)
    connection = RecordingConnection(
        "mssql", driver="pyodbc", raw=raw, fail_on=("ROLLBACK",)
    )

    def _fail() -> None:
        raise SQLAlchemyError("simulated failure")

    connection.rollback = _fail  # type: ignore[assignment]

    with pytest.raises(SQLAlchemyError, match="simulated failure"):
        with protected_query(connection, "SELECT 1", 5):
            pass

    assert connection.invalidated is True


# --------------------------------------------------------------------------
# SQLite defensive branches
# --------------------------------------------------------------------------
def test_sqlite_guard_requires_progress_handler_support():
    connection = RecordingConnection("sqlite", raw=object())

    with pytest.raises(QuerySecurityError, match="timeout support is unavailable"):
        with protected_query(connection, "SELECT 1", 5):
            pass


def test_sqlite_guard_fails_when_read_only_mode_cannot_be_enabled():
    raw = SimpleNamespace(set_progress_handler=lambda *args: None)
    connection = RecordingConnection(
        "sqlite", raw=raw, values={"PRAGMA query_only": [0, 0]}
    )

    with pytest.raises(QuerySecurityError, match="Could not enable SQLite read-only"):
        with protected_query(connection, "SELECT 1", 5):
            pass


def test_sqlite_guard_invalidates_the_connection_when_restoring_fails():
    raw = SimpleNamespace(set_progress_handler=lambda *args: None)
    connection = RecordingConnection(
        "sqlite",
        raw=raw,
        values={"PRAGMA query_only": [0, 1]},
        fail_on=("PRAGMA query_only = 0",),
    )

    with pytest.raises(SQLAlchemyError, match="simulated failure"):
        with protected_query(connection, "SELECT 1", 5):
            pass

    assert connection.invalidated is True


def test_mssql_guard_requires_timeout_support_on_the_driver():
    connection = RecordingConnection("mssql", driver="pyodbc", raw=object())

    with pytest.raises(QuerySecurityError, match="Query timeout is unsupported"):
        with protected_query(connection, "SELECT 1", 5):
            pass


# --------------------------------------------------------------------------
# PostgreSQL - exercised against the real server
# --------------------------------------------------------------------------
@pytest.fixture
def postgres_engine(internal_database: str):
    """A real PostgreSQL engine pointing at the internal test database."""
    from core.config import get_settings

    settings = get_settings()
    url = (
        f"postgresql+psycopg2://{settings.POSTGRES_USERNAME}:"
        f"{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:"
        f"{settings.POSTGRES_PORT}/{internal_database}"
    )

    engine = create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.mark.integration
def test_postgres_guard_enables_a_read_only_transaction(postgres_engine):
    with postgres_engine.connect() as connection:
        with protected_query(connection, "SELECT 1", 5) as safe_sql:
            assert connection.exec_driver_sql(safe_sql).scalar_one() == 1

            with pytest.raises(DBAPIError) as exc_info:
                connection.exec_driver_sql(
                    "CREATE TABLE guard_readonly_probe (id integer)"
                )
            assert "read-only" in str(exc_info.value).lower()

        # the transaction was rolled back, so the session is writable again
        connection.exec_driver_sql("CREATE TEMP TABLE guard_write_probe (id integer)")
        connection.exec_driver_sql("DROP TABLE guard_write_probe")


@pytest.mark.integration
def test_postgres_guard_applies_and_restores_the_statement_timeout(postgres_engine):
    with postgres_engine.connect() as connection:
        with protected_query(connection, "SELECT 1", 5):
            timeout = connection.exec_driver_sql("SHOW statement_timeout").scalar()
            assert timeout == "5s"

        assert connection.exec_driver_sql("SHOW statement_timeout").scalar() == "0"


@pytest.mark.integration
def test_postgres_guard_restores_the_timeout_after_an_exception(postgres_engine):
    with postgres_engine.connect() as connection:
        with pytest.raises(ValueError, match="boom"):
            with protected_query(connection, "SELECT 1", 5):
                raise ValueError("boom")

        assert connection.exec_driver_sql("SHOW statement_timeout").scalar() == "0"
        connection.exec_driver_sql("CREATE TEMP TABLE guard_write_probe (id integer)")
        connection.exec_driver_sql("DROP TABLE guard_write_probe")


@pytest.mark.integration
def test_postgres_guard_enforces_the_statement_timeout(postgres_engine):
    """A statement that runs longer than the timeout is cancelled."""
    with postgres_engine.connect() as connection:
        with pytest.raises(DBAPIError) as exc_info:
            # the validator is bypassed on purpose: this asserts the
            # transport level timeout, not the SQL validation.
            with protected_query(connection, "SELECT pg_sleep(5)", 1) as safe_sql:
                connection.exec_driver_sql(safe_sql)

        assert "statement timeout" in str(exc_info.value).lower()
        assert connection.exec_driver_sql("SHOW statement_timeout").scalar() == "0"
