"""Regression tests for the query executor (`database.query_executor`).

The executor is exercised against a real SQLite database.  Nothing is
mocked here: the validator, the read-only guard (`query_security`) and
SQLite itself all run for real.
"""

from __future__ import annotations

import time

import pytest

from database.connection import DatabaseConnectionManager
from database.query_executor import QueryExecutionError, QueryExecutor
from database.query_security import protected_query


# --------------------------------------------------------------------------
# Constructor validation
# --------------------------------------------------------------------------
@pytest.mark.parametrize("max_rows", [0, -1, 10001, True, "10", 10.0])
def test_invalid_max_rows_is_rejected(db_manager: DatabaseConnectionManager, max_rows):
    with pytest.raises(ValueError, match="max_rows"):
        QueryExecutor(db_manager, max_rows=max_rows)


@pytest.mark.parametrize("timeout", [0, -1, 3601, True, "5", None])
def test_invalid_timeout_is_rejected(db_manager: DatabaseConnectionManager, timeout):
    with pytest.raises(ValueError, match="timeout_seconds"):
        QueryExecutor(db_manager, timeout_seconds=timeout)


def test_executor_accepts_valid_configuration(db_manager: DatabaseConnectionManager):
    executor = QueryExecutor(db_manager, max_rows=10, timeout_seconds=1.5)
    assert executor is not None


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------
def test_select_returns_rows_and_columns(query_executor: QueryExecutor):
    result = query_executor.execute("SELECT id, name, city FROM customers ORDER BY id")

    assert result["data"]["columns"] == ["id", "name", "city"]
    assert result["data"]["row_count"] == 4
    assert result["data"]["truncated"] is False
    assert result["data"]["rows"][0] == {
        "id": 1,
        "name": "Alice",
        "city": "Berlin",
    }


def test_requested_sql_is_kept_and_executed_sql_is_normalised(query_executor: QueryExecutor):
    result = query_executor.execute("select   id from customers where id=1")

    assert result["requested_sql"] == "select   id from customers where id=1"
    assert result["executed_sql"] == "SELECT id FROM customers WHERE id = 1"


def test_query_without_matching_rows_reports_zero_rows(query_executor: QueryExecutor):
    result = query_executor.execute("SELECT id FROM customers WHERE id = 9999")

    assert result["data"]["row_count"] == 0
    assert result["data"]["rows"] == []
    assert result["data"]["truncated"] is False


def test_aggregate_query_is_supported(query_executor: QueryExecutor):
    result = query_executor.execute(
        "SELECT COUNT(*) AS orders_count, SUM(total) AS revenue FROM orders"
    )

    assert result["data"]["columns"] == ["orders_count", "revenue"]
    assert result["data"]["rows"][0]["orders_count"] == 5


def test_join_across_foreign_keys_is_supported(query_executor: QueryExecutor):
    result = query_executor.execute(
        "SELECT c.name AS customer_name, o.total AS order_total "
        "FROM customers c JOIN orders o ON o.customer_id = c.id "
        "ORDER BY o.id"
    )

    assert result["data"]["columns"] == ["customer_name", "order_total"]
    assert result["data"]["row_count"] == 5


# --------------------------------------------------------------------------
# Row truncation
# --------------------------------------------------------------------------
def test_result_set_is_truncated_at_the_max_row_limit(db_manager: DatabaseConnectionManager):
    executor = QueryExecutor(db_manager, max_rows=2, timeout_seconds=5)

    result = executor.execute("SELECT id FROM customers ORDER BY id")

    assert result["data"]["row_count"] == 2
    assert result["data"]["truncated"] is True
    assert [row["id"] for row in result["data"]["rows"]] == [1, 2]


def test_truncated_result_reports_the_total_row_count(db_manager: DatabaseConnectionManager):
    """The caller learns how many rows exist in total, not only how many fit."""
    executor = QueryExecutor(db_manager, max_rows=2, timeout_seconds=5)

    result = executor.execute("SELECT id FROM customers ORDER BY id")

    assert result["data"]["total_rows"] == 4
    assert result["data"]["row_count"] == 2


def test_result_set_is_not_truncated_when_it_fits(db_manager: DatabaseConnectionManager):
    executor = QueryExecutor(db_manager, max_rows=10, timeout_seconds=5)

    result = executor.execute("SELECT id FROM customers ORDER BY id")

    assert result["data"]["row_count"] == 4
    assert result["data"]["truncated"] is False
    assert result["data"]["total_rows"] == 4


def test_remaining_rows_are_counted_in_bounded_chunks():
    """The total row count must not be produced by loading every row."""

    class RecordingResult:
        def __init__(self, rows):
            self.rows = list(rows)
            self.chunk_sizes: list[int] = []

        def fetchmany(self, size):
            self.chunk_sizes.append(size)
            chunk, self.rows = self.rows[:size], self.rows[size:]
            return chunk

        def fetchall(self):
            raise AssertionError(
                "the executor must not load every remaining row at once"
            )

    result = RecordingResult(range(2500))

    total = QueryExecutor.count_remaining_rows(result, 1000)

    assert total == 2500
    # three full chunks plus a final empty one that ends the counting
    assert result.chunk_sizes == [1000, 1000, 1000, 1000]


def test_large_result_set_reports_the_total_row_count(tmp_path):
    """A result set far larger than the row limit is counted exactly."""
    import sqlite3

    path = tmp_path / "large.db"
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE big (id INTEGER PRIMARY KEY NOT NULL, value TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO big (id, value) VALUES (?, ?)",
            [(index, f"row-{index}") for index in range(5000)],
        )
        connection.commit()
    finally:
        connection.close()

    manager = DatabaseConnectionManager(f"sqlite:///{path.as_posix()}")
    try:
        executor = QueryExecutor(manager, max_rows=10, timeout_seconds=10)

        result = executor.execute("SELECT id FROM big ORDER BY id")

        assert result["data"]["row_count"] == 10
        assert result["data"]["total_rows"] == 5000
        assert result["data"]["truncated"] is True
    finally:
        manager.close()


def test_truncation_limit_of_one_row(db_manager: DatabaseConnectionManager):
    executor = QueryExecutor(db_manager, max_rows=1, timeout_seconds=5)

    result = executor.execute("SELECT id FROM orders")

    assert result["data"]["row_count"] == 1
    assert result["data"]["truncated"] is True


# --------------------------------------------------------------------------
# Timeouts
# --------------------------------------------------------------------------
@pytest.mark.slow
def test_slow_query_is_interrupted_by_the_timeout(db_manager: DatabaseConnectionManager):
    executor = QueryExecutor(db_manager, max_rows=100, timeout_seconds=1)

    started = time.monotonic()
    with pytest.raises(QueryExecutionError) as exc_info:
        executor.execute(
            "WITH RECURSIVE counter(value) AS ("
            "SELECT 1 UNION ALL SELECT value + 1 FROM counter WHERE value < 500000000"
            ") SELECT COUNT(*) FROM counter"
        )
    elapsed = time.monotonic() - started

    assert elapsed < 20, "the query was not interrupted by the configured timeout"
    assert "execution limits" in str(exc_info.value)
    assert exc_info.value.executed_sql is not None


@pytest.mark.slow
def test_database_is_usable_after_a_timeout(db_manager: DatabaseConnectionManager):
    executor = QueryExecutor(db_manager, max_rows=100, timeout_seconds=1)

    with pytest.raises(QueryExecutionError):
        executor.execute(
            "WITH RECURSIVE counter(value) AS ("
            "SELECT 1 UNION ALL SELECT value + 1 FROM counter WHERE value < 500000000"
            ") SELECT COUNT(*) FROM counter"
        )

    result = executor.execute("SELECT COUNT(*) AS c FROM customers")
    assert result["data"]["rows"][0]["c"] == 4


def test_fast_query_is_not_affected_by_the_timeout(db_manager: DatabaseConnectionManager):
    executor = QueryExecutor(db_manager, max_rows=100, timeout_seconds=5)

    result = executor.execute("SELECT id FROM customers")

    assert result["data"]["row_count"] == 4


# --------------------------------------------------------------------------
# Error handling
# --------------------------------------------------------------------------
def test_write_attempt_is_rejected_by_the_validator(query_executor: QueryExecutor):
    """Validation failures are surfaced as `QueryExecutionError`."""
    with pytest.raises(QueryExecutionError, match="Only SELECT queries are allowed"):
        query_executor.execute("DELETE FROM customers")


def test_rejected_query_is_never_executed(query_executor: QueryExecutor):
    with pytest.raises(QueryExecutionError) as exc_info:
        query_executor.execute("DELETE FROM customers")

    assert exc_info.value.executed_sql is None


def test_write_attempt_does_not_modify_the_database(query_executor: QueryExecutor):
    with pytest.raises(QueryExecutionError):
        query_executor.execute("DELETE FROM customers")

    result = query_executor.execute("SELECT COUNT(*) AS c FROM customers")
    assert result["data"]["rows"][0]["c"] == 4


def test_unknown_column_raises_an_execution_error(query_executor: QueryExecutor):
    with pytest.raises(QueryExecutionError) as exc_info:
        query_executor.execute("SELECT does_not_exist FROM customers")

    assert "SQL syntax" in str(exc_info.value)
    assert exc_info.value.executed_sql is not None


def test_unknown_table_raises_an_execution_error(query_executor: QueryExecutor):
    with pytest.raises(QueryExecutionError):
        query_executor.execute("SELECT * FROM missing_table")


def test_duplicate_column_names_are_rejected(query_executor: QueryExecutor):
    with pytest.raises(QueryExecutionError, match="Duplicate column names"):
        query_executor.execute(
            "SELECT c.id, o.id FROM customers c JOIN orders o ON o.customer_id = c.id"
        )


def test_blocked_function_is_rejected_before_execution(query_executor: QueryExecutor):
    with pytest.raises(QueryExecutionError, match="forbidden function"):
        query_executor.execute("SELECT pg_sleep(10)")


# --------------------------------------------------------------------------
# Read-only guard (`query_security.protected_query`)
# --------------------------------------------------------------------------
def test_read_only_guard_is_removed_after_the_query(db_manager: DatabaseConnectionManager):
    with db_manager.engine.connect() as connection:
        with protected_query(connection, "SELECT 1", 5) as safe_sql:
            assert connection.exec_driver_sql(safe_sql).scalar_one() == 1

        guard = connection.exec_driver_sql("PRAGMA query_only").scalar_one()
        assert int(guard) == 0


def test_read_only_guard_blocks_writes_inside_the_guard(db_manager: DatabaseConnectionManager):
    with db_manager.engine.connect() as connection:
        with protected_query(connection, "SELECT 1", 5):
            with pytest.raises(Exception):
                connection.exec_driver_sql(
                    "INSERT INTO customers (id, name, signup_date) VALUES (99, 'x', '2024-01-01')"
                )


def test_unsupported_backend_is_rejected(db_manager: DatabaseConnectionManager):
    from database.query_security import QuerySecurityError

    class _FakeConnection:
        dialect = type("Dialect", (), {"name": "oracle", "driver": "x"})()

    with pytest.raises(QuerySecurityError, match="Unsupported database backend"):
        with protected_query(_FakeConnection(), "SELECT 1", 5):
            pass


@pytest.mark.parametrize("timeout", [0, -1, 3601, "5"])
def test_invalid_timeout_is_rejected_by_the_guard(db_manager: DatabaseConnectionManager, timeout):
    with db_manager.engine.connect() as connection:
        with pytest.raises(ValueError, match="timeout"):
            with protected_query(connection, "SELECT 1", timeout):
                pass
