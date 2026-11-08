from fastapi import HTTPException, Request, status

from database.connection import DatabaseConnectionManager


def get_db_manager(request: Request) -> DatabaseConnectionManager:
    manager = request.app.state.db_manager

    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active database connection.",
        )

    return manager
