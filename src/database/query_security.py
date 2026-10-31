from contextlib import contextmanager
from math import ceil, isfinite
from time import monotonic

from sqlalchemy.engine import Connection


class QuerySecurityError(Exception):
    pass

def _restore(conn: Connection, *statements: str, rollback: bool = False):
    
    try:
        if rollback:
            conn.rollback()
        for sql in statements:
            conn.exec_driver_sql(sql)
    except Exception:
        conn.invalidate()
        raise


@contextmanager
def _sqlite(conn: Connection, sql: str, timeout: float):
    
    raw = conn.connection.driver_connection
    if not hasattr(raw, "set_progress_handler"):
        raise QuerySecurityError("SQLite timeout support is unavailable.")

    previous = int(conn.exec_driver_sql("PRAGMA query_only").scalar_one())
    try:
        conn.exec_driver_sql("PRAGMA query_only = ON")
        if int(conn.exec_driver_sql("PRAGMA query_only").scalar_one()) != 1:
            raise QuerySecurityError("Could not enable SQLite read-only mode.")

        deadline = monotonic() + timeout
        raw.set_progress_handler(lambda: int(monotonic() >= deadline), 1000)
        
        yield sql
        
    finally:
        try:
            raw.set_progress_handler(None, 0)
            _restore(conn, f"PRAGMA query_only = {previous}", rollback=True)
        except Exception:
            conn.invalidate()
            raise


@contextmanager
def _postgresql(conn: Connection, sql: str, timeout: float):
    
    try:
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        conn.exec_driver_sql(f"SET LOCAL statement_timeout = {ceil(timeout * 1000)}")
        
        yield sql
        
    finally:
        _restore(conn, rollback=True)


@contextmanager
def _mysql(conn: Connection, sql: str, timeout: float):
    
    is_mariadb = (
        conn.dialect.name == "mariadb"
        or getattr(conn.dialect, "is_mariadb", False)
    )
    previous = None
    
    try:
        if is_mariadb:
            seconds = ceil(timeout * 1000) / 1000
            safe_sql = f"SET STATEMENT max_statement_time={seconds} FOR {sql}"
        else:
            previous = int(conn.exec_driver_sql("SELECT @@SESSION.max_execution_time").scalar_one())
            conn.exec_driver_sql(f"SET SESSION max_execution_time = {ceil(timeout * 1000)}")
            safe_sql = sql

        conn.exec_driver_sql("START TRANSACTION READ ONLY")
        
        yield safe_sql
        
    finally:
        changes = (
            (f"SET SESSION max_execution_time = {previous}",)
            if previous is not None else ()
        )
        _restore(conn, *changes, rollback=True)


@contextmanager
def _mssql(conn: Connection, sql: str, timeout: float):
    
    if conn.dialect.driver != "pyodbc":
        raise QuerySecurityError("SQL Server requires the pyodbc driver.")

    raw = conn.connection.driver_connection
    if not hasattr(raw, "timeout"):
        raise QuerySecurityError("Query timeout is unsupported by this driver.")

    previous = raw.timeout
    try:
        raw.timeout = ceil(timeout)
        
        yield sql
    
    finally:
        try:
            raw.timeout = previous
            _restore(conn, rollback=True)
        except Exception:
            conn.invalidate()
            raise


_BACKENDS = {
    "sqlite": _sqlite,
    "postgresql": _postgresql,
    "mysql": _mysql,
    "mariadb": _mysql,
    "mssql": _mssql,
}

@contextmanager
def protected_query(conn: Connection, sql: str, timeout: float):
    
    if not isinstance(timeout, (int, float)) or not isfinite(timeout) or not 0 < timeout <= 3600:
        raise ValueError("timeout must be greater than 0 and at most 3600 seconds.")

    backend = _BACKENDS.get(conn.dialect.name)
    if backend is None:
        raise QuerySecurityError("Unsupported database backend.")

    with backend(conn, sql, timeout) as safe_sql:
        yield safe_sql