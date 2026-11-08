from typing import Literal

from pydantic import BaseModel


class ConnectionResponse(BaseModel):
    status: Literal["connected"]
    dialect: str
    
class SchemaTablesResponse(BaseModel):
    tables: list[str]

class ColumnResponse(BaseModel):
    name: str
    type: str
    nullable: bool
    
class ForeignKeyResponse(BaseModel):
    columns: list[str]
    referred_schema: str | None = None
    referred_table: str
    referred_columns: list[str]
    
class TableSchemaResponse(BaseModel):
    table_name: str
    columns: list[ColumnResponse]
    primary_key: list[str]
    foreign_keys: list[ForeignKeyResponse]