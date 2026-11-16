from fastapi import HTTPException, Request, status

from database.connection import DatabaseConnectionManager


def get_db_manager(request: Request) -> DatabaseConnectionManager:
    manager = getattr(request.app.state, "db_manager", None)

    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active database connection.",
        )

    return manager

async def get_internal_db(request: Request):
    session_factory = getattr(request.app.state, "db_client", None)

    if not session_factory:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal database session factory is not initialized.",
        )

    async with session_factory() as session:
        yield session