import json
from typing import Annotated, Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field, ValidationError

from database.connection import DatabaseConnectionManager
from database.query_executor import QueryExecutionError, QueryExecutor
from database.query_validator import QueryValidationError
from database.schema_inspector import SchemaInspectionError, SchemaInspector
from models.pydantic_schemas.agent_tool_inputs import DatabaseToolInput

ToolResult = tuple[str, dict[str, Any]]

SchemaName = Annotated[
    str | None, Field(description="Optional database schema name."),
]

TableName = Annotated[
    str, Field(description="Name of the table to inspect."),
]

SQLQuery = Annotated[
    str,
    Field(description=(
            "A single, valid read-only SQL SELECT query. "
            "Always use explicit column aliases (AS) when joining tables "
            "to avoid duplicate column names."
        )),
]

def _to_json(data: Any):
    return json.dumps(data, ensure_ascii=False, default=str)

def _schema_success(tool_name: str, data: Any) -> ToolResult:
    artifact = {
        "tool_name": tool_name,
        "status": "success",
        "data": data,
        "error": None,
    }
    return _to_json(data), artifact

def _schema_failure(tool_name: str, exc: Exception) -> ToolResult:
    error = str(exc)
    artifact = {
        "tool_name": tool_name,
        "status": "failed",
        "data": None,
        "error": error,
    }
    return f"Schema inspection failed: {error}", artifact

def _sql_success(execution: dict[str, Any]) -> ToolResult: 
    artifact = {
        "requested_sql": execution["requested_sql"],
        "executed_sql": execution["executed_sql"],
        "status": "success",
        "data": execution["data"],
        "error": None,
    }
    content = _to_json({"executed_sql": execution["executed_sql"], "data": execution["data"]})
    return content, artifact


def _sql_failure(requested_sql: str, error: str,
                label: str | None = None,
                executed_sql: str | None = None) -> ToolResult:
    artifact = {
        "requested_sql": requested_sql,
        "executed_sql": executed_sql,
        "status": "failed",
        "data": None,
        "error": error,
    }
    return (f"{label}: {error}" if label else error), artifact


class SQLTools:
    
    def __init__(self, manager: DatabaseConnectionManager) -> None:
        self._inspector = SchemaInspector(manager.engine)
        self._executor = QueryExecutor(manager)

        self.list_tables = self._as_tool("list_tables", self._list_tables)
        self.describe_table = self._as_tool("describe_table", self._describe_table)
        self.execute_sql_query = self._as_tool("execute_sql_query", self._execute_sql_query)

    @staticmethod
    def _as_tool(name: str, func) -> BaseTool:
        return StructuredTool.from_function(
            func=func,
            name=name,
            response_format="content_and_artifact",
        )

    def get_tools(self) -> list[BaseTool]:
        return [self.list_tables, self.describe_table, self.execute_sql_query]

    def _list_tables(self, schema_name: SchemaName = None) -> ToolResult:
        """
        List tables in the connected database. Use this tool
        to discover available tables before writing SQL.

        Args:
            schema_name (str | None): Optional database schema to inspect.

        Returns:
            str: JSON list of available table names, or an error message.
        """
        inputs = DatabaseToolInput(schema_name=schema_name)

        try:
            tables = self._inspector.list_tables(schema=inputs.schema_name)
        except SchemaInspectionError as exc:
            return _schema_failure("list_tables", exc)

        return _schema_success("list_tables", tables)

    def _describe_table(self, table_name: TableName, schema_name: SchemaName = None) -> ToolResult:
        """
        Describe a table's columns, data types, primary key,
        and foreign keys. Use this tool to understand table
        structure before generating SQL queries.

        Args:
            table_name (str): Name of the table to inspect.
            schema_name (str | None): Optional database schema.

        Returns:
            str: JSON table metadata, including columns and relationships, or an error message.
        """
        inputs = DatabaseToolInput(table_name=table_name, schema_name=schema_name)

        try:
            columns = self._inspector.get_table_columns(
                table_name=inputs.table_name,
                schema=inputs.schema_name,
            )
            relationships = self._inspector.get_table_relationships(
                table_name=inputs.table_name,
                schema=inputs.schema_name,
            )
        except SchemaInspectionError as exc:
            return _schema_failure("describe_table", exc)

        data = {
            "table_name": inputs.table_name,
            "schema": inputs.schema_name,
            "columns": columns,
            **relationships,
        }
        return _schema_success("describe_table", data)

    def _execute_sql_query(self, query: SQLQuery) -> ToolResult:
        """
        Execute a read-only SQL SELECT query against the database and return the results.
        Use this tool ONLY after inspecting table names and column structures using
        'list_tables' and 'describe_table'. Do not guess table or column names.

        Args:
            query (str): SQL SELECT query to validate and execute.

        Returns:
            str: JSON with the executed SQL and its results (columns, rows,
                row count, and truncation status), or an error message.
        """
        try:
            sql = DatabaseToolInput(query=query).query
        except ValidationError:
            return _sql_failure(query, "Invalid SQL tool input.")

        try:
            execution = self._executor.execute(sql)
        except QueryValidationError as exc:
            return _sql_failure(sql, str(exc), label="SQL validation failed")
        except QueryExecutionError as exc:
            return _sql_failure(
                sql,
                str(exc),
                label="SQL execution failed",
                executed_sql=exc.executed_sql,
            )

        return _sql_success(execution)