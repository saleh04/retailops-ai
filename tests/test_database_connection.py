"""Regression tests for the connection manager (`database.connection`).

Everything here runs against real URLs - no database server is mocked.  The
failure cases use URLs that cannot be parsed, dialects that are not
installed, or a port where nothing is listening.
"""

from __future__ import annotations

import pytest

from core.config import get_settings
from database.connection import (
    DatabaseConnectionError,
    DatabaseConnectionManager,
    connect,
)

# Nothing is listening on port 1, so connecting fails immediately.
UNREACHABLE_POSTGRES = "postgresql+psycopg2://postgres:secret@localhost:1/missing"


# --------------------------------------------------------------------------
# URL validation
# --------------------------------------------------------------------------
@pytest.mark.parametrize("url", ["", "   ", "\n"])
def test_empty_url_is_rejected(url: str):
    with pytest.raises(DatabaseConnectionError, match="cannot be empty"):
        DatabaseConnectionManager(url)


def test_unparsable_url_is_rejected():
    with pytest.raises(DatabaseConnectionError, match="Invalid database URL format"):
        DatabaseConnectionManager("not-a-database-url")


def test_safe_url_hides_the_password():
    manager = DatabaseConnectionManager(
        "postgresql+psycopg2://postgres:super-secret@localhost:5432/retailops"
    )

    assert "super-secret" not in manager.safe_url
    assert "postgres" in manager.safe_url


@pytest.mark.parametrize(
    ("url", "backend"),
    [
        ("sqlite:///data.db", "sqlite"),
        ("postgresql://user:pw@host:5432/db", "postgresql"),
        ("mysql+pymysql://user:pw@host:3306/db", "mysql"),
        ("mariadb+pymysql://user:pw@host:3306/db", "mariadb"),
    ],
)
def test_backend_name_is_derived_from_the_url(url: str, backend: str):
    assert DatabaseConnectionManager(url).database == backend


# --------------------------------------------------------------------------
# Engine creation
# --------------------------------------------------------------------------
def test_unknown_dialect_is_reported():
    manager = DatabaseConnectionManager("notadialect://host/db")

    with pytest.raises(DatabaseConnectionError) as exc_info:
        manager.connect()

    assert "Unsupported database dialect 'notadialect'" in str(exc_info.value)
    assert "missing database driver" in str(exc_info.value)


def test_missing_third_party_driver_is_reported():
    """A known dialect whose driver is not installed cannot be created."""
    manager = DatabaseConnectionManager("oracle://user:pw@host:1521/db")

    with pytest.raises(DatabaseConnectionError) as exc_info:
        manager.connect()

    assert str(exc_info.value) == "Failed to initialize database engine."


def test_engine_is_created_only_once():
    manager = DatabaseConnectionManager("sqlite:///:memory:")

    engine = manager.connect()

    assert manager.connect() is engine
    assert manager.engine is engine

    manager.close()


def test_close_releases_the_engine():
    manager = DatabaseConnectionManager("sqlite:///:memory:")
    manager.connect()

    manager.close()

    assert manager._engine is None  # noqa: SLF001 - the closed state is the contract


def test_context_manager_connects_and_closes():
    with DatabaseConnectionManager("sqlite:///:memory:") as manager:
        assert manager.engine is not None
        engine = manager.engine

    assert manager._engine is None  # noqa: SLF001 - the closed state is the contract
    assert engine.pool is not None


# --------------------------------------------------------------------------
# Connection arguments
# --------------------------------------------------------------------------
def test_sqlite_connect_arguments():
    manager = DatabaseConnectionManager("sqlite:///:memory:")

    assert manager._get_connect_args() == {  # noqa: SLF001
        "timeout": get_settings().CONNECT_TIMEOUT
    }


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:pw@host:5432/db",
        "mysql://user:pw@host:3306/db",
        "mariadb://user:pw@host:3306/db",
    ],
)
def test_server_connect_arguments(url: str):
    manager = DatabaseConnectionManager(url)

    assert manager._get_connect_args() == {  # noqa: SLF001
        "connect_timeout": get_settings().CONNECT_TIMEOUT
    }


def test_unknown_backend_has_no_connect_arguments():
    manager = DatabaseConnectionManager("notadialect://host/db")

    assert manager._get_connect_args() == {}  # noqa: SLF001


# --------------------------------------------------------------------------
# Connection verification
# --------------------------------------------------------------------------
def test_test_connection_succeeds_for_a_reachable_database(tmp_path):
    manager = DatabaseConnectionManager(f"sqlite:///{tmp_path.as_posix()}/probe.db")

    assert manager.test_connection() is True

    manager.close()


def test_test_connection_fails_for_an_unreachable_server():
    manager = DatabaseConnectionManager(UNREACHABLE_POSTGRES)

    with pytest.raises(DatabaseConnectionError) as exc_info:
        manager.test_connection()

    assert "Unable to establish database connection" in str(exc_info.value)
    assert "Check credentials and server availability" in str(exc_info.value)

    manager.close()


def test_connect_helper_returns_a_verified_manager(tmp_path):
    manager = connect(f"sqlite:///{tmp_path.as_posix()}/probe.db")

    try:
        assert manager.engine is not None
        assert manager.database == "sqlite"
    finally:
        manager.close()


def test_connect_helper_closes_the_manager_when_the_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    closed: list[DatabaseConnectionManager] = []
    original_close = DatabaseConnectionManager.close

    def _spy(self: DatabaseConnectionManager) -> None:
        closed.append(self)
        original_close(self)

    monkeypatch.setattr(DatabaseConnectionManager, "close", _spy)

    with pytest.raises(DatabaseConnectionError):
        connect(UNREACHABLE_POSTGRES)

    assert len(closed) == 1
    assert closed[0]._engine is None  # noqa: SLF001 - the closed state is the contract
