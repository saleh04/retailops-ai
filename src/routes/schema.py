import logging

from fastapi import APIRouter, Depends, HTTPException, status

from database.connection import DatabaseConnectionManager
from database.schema_inspector import (
    SchemaInspectionError,
    SchemaInspector,
    TableNotFoundError,
)
from models.pydantic_schemas.api_responses import (
    SchemaTablesResponse,
    TableSchemaResponse,
)
from routes.dependencies import get_db_manager

logger = logging.getLogger(__name__)

schema_router = APIRouter(
    prefix="/api/v1/schema",
    tags=["Schema"],
)


@schema_router.get("/tables", response_model=SchemaTablesResponse)
def list_tables(schema_name: str | None = None,
                manager: DatabaseConnectionManager = Depends(get_db_manager)):  # noqa: B008
    try:
        inspector = SchemaInspector(manager.engine)
        return SchemaTablesResponse(tables=inspector.list_tables(schema=schema_name))

    except SchemaInspectionError:
        logger.exception("Failed to retrieve database tables.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve database tables.",
        ) from None


@schema_router.get("/tables/{table_name}", response_model=TableSchemaResponse)
def describe_table(table_name: str, schema_name: str | None = None,
                    manager: DatabaseConnectionManager = Depends(get_db_manager)):  # noqa: B008
    try:
        inspector = SchemaInspector(manager.engine)
        return TableSchemaResponse(
            table_name=table_name,
            columns=inspector.get_table_columns(table_name, schema=schema_name),
            **inspector.get_table_relationships(table_name, schema=schema_name),
        )

    except TableNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_name}' was not found.",
        ) from None

    except SchemaInspectionError:
        logger.exception(f"Failed to inspect table. {table_name}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not inspect database table.",
        ) from None