from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


class SchemaInspectionError(Exception):
    pass

class TableNotFoundError(SchemaInspectionError):
    pass

class SchemaInspector:
    
    def __init__(self, engine: Engine) -> None:
        
        try:
            self._inspector = inspect(engine)
        except SQLAlchemyError as e:
            raise SchemaInspectionError(
                "Could not inspect database connection."
            ) from e
                        
    def list_tables(self, schema: str | None=None) -> list:
        
        try:
            return self._inspector.get_table_names(schema=schema)
        except SQLAlchemyError as e:
            raise SchemaInspectionError(
                "Could not list database tables."
            ) from e 
            
    def is_table_exists(self, table_name: str, schema: str | None = None) -> bool:
        return table_name in self.list_tables(schema=schema)

    def _read_table_columns(self, table_name: str, schema: str | None = None) -> list[dict]:
        try:
            columns = self._inspector.get_columns(table_name=table_name, schema=schema)
        except SQLAlchemyError as e:
            raise SchemaInspectionError(
                f"Could not read columns for '{table_name}'."
            ) from e
            
        return [
            {
                "name": column["name"],
                "type": str(column["type"]),
                "nullable": column["nullable"],
            }
            for column in columns 
        ]

    def get_table_columns(self, table_name: str, schema: str | None = None) -> list[dict]:
        if not self.is_table_exists(table_name, schema=schema):
            raise TableNotFoundError(f"Table '{table_name}' was not found.")
        return self._read_table_columns(table_name, schema=schema)

    def _read_table_relationships(self, table_name: str, schema: str | None = None) -> dict:
        try:
            pk = self._inspector.get_pk_constraint(table_name=table_name, schema=schema)
            fk = self._inspector.get_foreign_keys(table_name=table_name, schema=schema)
        except SQLAlchemyError as e:
            raise SchemaInspectionError(
                f"Could not read keys for '{table_name}'."
            ) from e
            
        return {
            "primary_key": pk.get("constrained_columns") or [],
            "foreign_keys": [
                {
                    "columns": foreign_key["constrained_columns"],
                    "referred_schema": foreign_key.get("referred_schema"),
                    "referred_table": foreign_key["referred_table"],
                    "referred_columns": foreign_key["referred_columns"],
                }
                for foreign_key in fk
            ],
        }

    def get_table_relationships(self, table_name: str, schema: str | None = None) -> dict:
        if not self.is_table_exists(table_name, schema=schema):
            raise TableNotFoundError(f"Table '{table_name}' was not found.")
        return self._read_table_relationships(table_name, schema=schema)
        
    def get_database_schema(self, schema: str | None = None) -> dict:
        
        result = {}

        for table_name in self.list_tables(schema=schema):
            result[table_name] = {
                "columns": self._read_table_columns(
                    table_name, schema=schema
                ),
                **self._read_table_relationships(
                    table_name, schema=schema
                ),
            }

        return result