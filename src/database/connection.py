import logging
from typing import Self

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.exc import ArgumentError, NoSuchModuleError, SQLAlchemyError

from src.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class DatabaseConnectionError(Exception):
    pass

class DatabaseConnectionManager:

    def __init__(self, database_url: str) -> None:
        self._raw_url: str = database_url
        self._parsed_url: URL = self._validate_and_parse_url(database_url)
        self._engine: Engine | None = None

    @staticmethod
    def _validate_and_parse_url(database_url: str) -> URL:
        if not database_url or not database_url.strip():
            raise DatabaseConnectionError("Database connection URL cannot be empty.")

        try:
            return make_url(database_url)
        except ArgumentError as e:
            raise DatabaseConnectionError(
                "Invalid database URL format."
            ) from e

    @property
    def safe_url(self) -> str:
        return self._parsed_url.render_as_string(hide_password=True)

    @property
    def database(self) -> str:
        return self._parsed_url.get_backend_name()

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            return self.connect()
        return self._engine

    def _get_connect_args(self) -> dict:
        timeout = settings.CONNECT_TIMEOUT
        if self.database == "sqlite":
            return {"timeout": timeout}
        if self.database in ("postgresql", "mysql", "mariadb"):
            return {"connect_timeout": timeout}
        return {}

    def connect(self) -> Engine:
        if self._engine is not None:
            return self._engine

        try:
            logger.info(f"Initializing {self.database} engine for: {self.safe_url}")

            self._engine = create_engine(
                self._parsed_url,
                pool_pre_ping=settings.POOL_PRE_PING,
                connect_args=self._get_connect_args(),
            )
            return self._engine

        except NoSuchModuleError:
            raise DatabaseConnectionError(
                f"Unsupported database dialect '{self.database}' "
                "or missing database driver."
            ) from None

        except Exception:
            raise DatabaseConnectionError(
                "Failed to initialize database engine."
            ) from None

    def test_connection(self) -> bool:

        engine = self.connect()
        
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            logger.info(f"Database connection verified successfully: {self.safe_url}")
            return True
        
        except SQLAlchemyError:
            logger.error(
                "Database connection test failed for %s",
                self.database
            )
            raise DatabaseConnectionError(
                "Unable to establish database connection. "
                "Check credentials and server availability."
            ) from None

    def close(self) -> None:
        
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            logger.info(f"Database connection pool closed: {self.safe_url}")

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def connect(database_url: str) -> DatabaseConnectionManager:
    manager = DatabaseConnectionManager(database_url)

    try:
        manager.test_connection()
    except Exception:
        manager.close()
        raise

    return manager