from math import isfinite

from sqlalchemy.exc import SQLAlchemyError

from .connection import DatabaseConnectionManager
from .query_security import QuerySecurityError, protected_query
from .query_validator import QueryValidator


class QueryExecutionError(Exception):
    pass

class QueryExecutor:
    
    def __init__(
        self,
        manager: DatabaseConnectionManager,
        max_rows: int = 100,
        timeout_seconds: float = 5,
    ):
        
        if not isinstance(max_rows, int) or isinstance(max_rows, bool) or not 1 <= max_rows <= 10_000:
            raise ValueError("max_rows must be between 1 and 10000.")
        if not isinstance(timeout_seconds, (int, float)) or not isfinite(timeout_seconds) or not 0 < timeout_seconds <= 3600:
            raise ValueError("timeout_seconds must be between 0 and 3600.")

        self._manager = manager
        self._validator = QueryValidator(manager.database)
        self._max_rows = max_rows
        self._timeout_seconds = timeout_seconds

    def execute(self, query: str) -> dict:
        
        sql = self._validator.validate(query)
        
        try:
            with self._manager.engine.connect() as conn:  # noqa: SIM117
                with protected_query(conn, sql, self._timeout_seconds) as safe_sql:
                    result = conn.exec_driver_sql(safe_sql)
                    
                    try:
                        if not result.returns_rows:
                            raise QueryExecutionError("Query did not return rows.")

                        columns = list(result.keys())
                        if len(columns) != len(set(columns)):
                            raise QueryExecutionError("Duplicate column names; use aliases.")

                        fetched = result.fetchmany(self._max_rows + 1)
                        rows = [
                            dict(zip(columns, row))
                            for row in fetched[:self._max_rows]
                        ]
                        return {
                            "columns": columns,
                            "rows": rows,
                            "row_count": len(rows),
                            "truncated": len(fetched) > self._max_rows,
                        }
                        
                    finally:
                        result.close()

        except QueryExecutionError:
            raise
        except (SQLAlchemyError, QuerySecurityError):
            raise QueryExecutionError(
                "Query failed: check SQL syntax, permissions, or execution limits."
            ) from None
        except Exception:  # noqa: BLE001
            raise QueryExecutionError("Query execution failed.") from None