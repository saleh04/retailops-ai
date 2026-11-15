import hashlib

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import DatabaseConnectionManager
from models.db_schemas import ConnectionRecord


class ConnectionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, manager: DatabaseConnectionManager):
        safe_url = manager.safe_url
        fingerprint = hashlib.sha256(safe_url.encode("utf-8")).hexdigest()

        result = await self.db.execute(
            select(ConnectionRecord).where(ConnectionRecord.fingerprint == fingerprint)
        )
        record = result.scalar_one_or_none()

        if record is None:
            record = ConnectionRecord(
                fingerprint=fingerprint,
                dialect=manager.database,
                safe_url=safe_url,
                database_name=make_url(safe_url).database
            )
            self.db.add(record)
        else:
            record.last_connected_at = func.now()

        await self.db.flush()
        return record.id