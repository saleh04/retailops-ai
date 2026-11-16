from math import isfinite

from sqlalchemy.exc import SQLAlchemyError

from .connection import DatabaseConnectionManager
from .query_security import QuerySecurityError, protected_query
from .query_validator import QueryValidationError, QueryValidator


class QueryExecutionError(Exception):

    def __init__(self, message: str, executed_sql: str | None = None):
        
        super().__init__(message)
        self.executed_sql = executed_sql

class QueryExecutor:

    COUNT_CHUNK_SIZE = 1000

    def __init__(self, manager: DatabaseConnectionManager,
                max_rows: int = 100, timeout_seconds: float = 5):

        if (
            not isinstance(max_rows, int)
            or isinstance(max_rows, bool)
            or not 1 <= max_rows <= 10000
        ):
            raise ValueError("max_rows must be between 1 and 10000.")

        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 3600
        ):
            raise ValueError("timeout_seconds must be a number between 0 and 3600.")

        self._manager = manager
        self._validator = QueryValidator(manager.database)
        self._max_rows = max_rows
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def count_remaining_rows(result, chunk_size: int) -> int:
        total = 0

        while True:
            chunk = result.fetchmany(chunk_size)
            if not chunk:
                return total
            total += len(chunk)

    def execute(self, query: str) -> dict:
        try:
            sql = self._validator.validate(query)
        except QueryValidationError as exc:
            raise QueryExecutionError(str(exc)) from exc

        execution_started = False
        try:
            with self._manager.engine.connect() as conn:  # noqa: SIM117
                with protected_query(conn, sql, self._timeout_seconds) as safe_sql:

                    execution_started = True
                    result = conn.exec_driver_sql(safe_sql)

                    try:
                        if not result.returns_rows:
                            raise QueryExecutionError(
                                "Query did not return rows.",
                                executed_sql=sql,
                            )

                        columns = list(result.keys())
                        if len(columns) != len(set(columns)):
                            raise QueryExecutionError(
                                "Duplicate column names; use aliases.",
                                executed_sql=sql,
                            )

                        fetched = result.fetchmany(self._max_rows + 1)
                        truncated = len(fetched) > self._max_rows
                        rows = [
                            dict(zip(columns, row))
                            for row in fetched[:self._max_rows]
                        ]

                        if truncated:
                            total_rows = len(fetched) + self.count_remaining_rows(
                                result, self.COUNT_CHUNK_SIZE
                            )
                        else:
                            total_rows = len(rows)

                        data = {
                            "columns": columns,
                            "rows": rows,
                            "row_count": len(rows),
                            "total_rows": total_rows,
                            "truncated": truncated,
                        }

                        return {
                            "requested_sql": query,
                            "executed_sql": sql,
                            "data": data
                        }

                    finally:
                        result.close()

        except QueryExecutionError:
            raise

        except (SQLAlchemyError, QuerySecurityError):
            raise QueryExecutionError(
                "Query failed: check SQL syntax, permissions, "
                "or execution limits.",
                executed_sql=sql if execution_started else None,
            ) from None

        except Exception:  # noqa: BLE001
            raise QueryExecutionError(
                "Query execution failed.",
                executed_sql=sql if execution_started else None,
            ) from None