import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from database.connection import DatabaseConnectionError, connect
from database.repositories import ConnectionRepository
from models.pydantic_schemas import ConnectionRequest, ConnectionResponse
from routes.dependencies import get_internal_db

logger = logging.getLogger(__name__)

connections_router = APIRouter(
    prefix="/api/v1/connections",
    tags=["Connections"],
)


@connections_router.get("", response_model=ConnectionResponse)
def get_connection_status(request: Request):
    manager = getattr(request.app.state, "db_manager", None)
    connection_id = getattr(request.app.state, "connection_id", None)

    if manager is None or connection_id is None:
        return ConnectionResponse(status="disconnected")

    return ConnectionResponse(
        status="connected",
        dialect=manager.database,
        connection_id=connection_id,
    )


@connections_router.post("", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_connection(payload: ConnectionRequest, request: Request,
                        db: AsyncSession = Depends(get_internal_db)):  # noqa: B008

    if getattr(request.app.state, "db_manager", None) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A database connection is already active.",
        )

    try:
        manager = await run_in_threadpool(
            connect,
            payload.database_url.get_secret_value(),
        )
    except DatabaseConnectionError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to connect to database.",
        ) from None

    try:
        connection_id = await ConnectionRepository(db).register(manager)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        manager.close()
        logger.exception("Failed to register the database connection.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not register database connection.",
        ) from None

    request.app.state.db_manager = manager
    request.app.state.connection_id = connection_id

    return ConnectionResponse(
        status="connected",
        dialect=manager.database,
        connection_id=connection_id,
    )


@connections_router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(request: Request):
    manager = getattr(request.app.state, "db_manager", None)

    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active database connection.",
        )

    try:
        manager.close()
    except Exception:
        logger.exception("Failed to close the database connection.")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not close database connection.",
        ) from None

    request.app.state.db_manager = None
    request.app.state.connection_id = None

    return Response(status_code=status.HTTP_204_NO_CONTENT)