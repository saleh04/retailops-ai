from typing import Annotated

from langchain_core.tools import BaseTool, tool
from pydantic import Field

from database.connection import DatabaseConnectionManager
from database.query_executor import QueryExecutor
from database.schema_inspector import SchemaInspector
from models.pydantic_schemas.agent_tool_inputs import DatabaseToolInput


class SQLTools:

    def __init__(self, manager: DatabaseConnectionManager) -> None:
        
        self._inspector = SchemaInspector(manager.engine)
        self._executor = QueryExecutor(manager)

        self.list_tables = self._create_list_tables()
        self.describe_table = self._create_describe_table()
        self.execute_sql_query = self._create_execute_sql_query()

    def _create_list_tables(self) -> BaseTool:

        @tool
        def list_tables(
            schema_name: Annotated[
                str | None,
                Field(description="Optional database schema name."),
            ] = None,
        ) -> list[str]:
            """
            List tables in the connected database. Use this tool
            to discover available tables before writing SQL.

            Args:
                schema_name (str | None): Optional database schema to inspect.

            Returns:
                list[str]: Names of available database tables.
            """
            inputs = DatabaseToolInput(schema_name=schema_name)

            return self._inspector.list_tables(
                schema=inputs.schema_name
            )

        return list_tables

    def _create_describe_table(self) -> BaseTool:

        @tool
        def describe_table(
            table_name: Annotated[
                str,
                Field(description="Name of the table to inspect."),
            ],
            schema_name: Annotated[
                str | None,
                Field(description="Optional database schema name."),
            ] = None,
        ) -> dict:
            """
            Describe a table's columns, data types, primary key,
            and foreign keys. Use this tool to understand table
            structure before generating SQL queries.

            Args:
                table_name (str): Name of the table to inspect.
                schema_name (str | None): Optional database schema.

            Returns:
                dict: Table metadata, including columns and relationships.
            """
            inputs = DatabaseToolInput(
                table_name=table_name,
                schema_name=schema_name,
            )

            columns = self._inspector.get_table_columns(
                table_name=inputs.table_name,
                schema=inputs.schema_name,
            )

            relationships = self._inspector.get_table_relationships(
                table_name=inputs.table_name,
                schema=inputs.schema_name,
            )

            return {
                "table_name": inputs.table_name,
                "schema": inputs.schema_name,
                "columns": columns,
                **relationships,
            }

        return describe_table

    def _create_execute_sql_query(self) -> BaseTool:

        @tool
        def execute_sql_query(
            query: Annotated[
                str,
                Field(description=
                        "A single, valid read-only SQL SELECT query. "
                        "Always use explicit column aliases (AS) when joining tables "
                        "to avoid duplicate column names."
                    ),
            ],
        ) -> dict:
            
            """
            Execute a read-only SQL SELECT query against the database and return the results.
            Use this tool ONLY after inspecting table names and column structures using
            'list_tables' and 'describe_table'. Do not guess table or column names.

            Args:
                query (str): SQL SELECT query to validate and execute.

            Returns:
                dict: Query columns, rows, row count, and truncation status.
            """
            inputs = DatabaseToolInput(query=query)

            return self._executor.execute(inputs.query)

        return execute_sql_query

    def get_tools(self) -> list[BaseTool]:
        """
        Return the database tools available to the AI agent.

        Returns:
            list[BaseTool]: Three independently callable LangChain tools.
        """
        return [
            self.list_tables,
            self.describe_table,
            self.execute_sql_query,
        ]
