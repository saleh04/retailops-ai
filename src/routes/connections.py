import logging

from fastapi import APIRouter, HTTPException, Request, Response, status

from database.connection import DatabaseConnectionError, connect
from models.pydantic_schemas.api_responses import ConnectionResponse
from models.pydantic_schemas.requests import ConnectionRequest

logger = logging.getLogger(__name__)

connections_router = APIRouter(
    prefix="/api/v1/connections",
    tags=["Connections"],
)


@connections_router.post("", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_connection(payload: ConnectionRequest, request: Request):
    if request.app.state.db_manager is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A database connection is already active.",
        )

    try:
        manager = connect(payload.database_url.get_secret_value())
    except DatabaseConnectionError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to connect to database.",
        ) from None

    request.app.state.db_manager = manager

    return ConnectionResponse(
        status="connected",
        dialect=manager.database,
    )


@connections_router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(request: Request):
    manager = request.app.state.db_manager

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

    return Response(status_code=status.HTTP_204_NO_CONTENT)