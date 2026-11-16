"""Regression tests for the agent's database tools (`agents.tools.sql_tools`).

The tools are the boundary between the LLM and the secured database layer:
they translate validator, executor and inspector failures into artifacts the
agent can react to.  Everything runs against a real SQLite database - only
the tool *arguments* are crafted by the test.
"""

from __future__ import annotations

import json

import pytest

from agents.tools.sql_tools import SQLTools
from database.connection import DatabaseConnectionManager


@pytest.fixture
def tools(db_manager: DatabaseConnectionManager) -> dict:
    """The three database tools exposed to the agent."""
    return {tool.name: tool for tool in SQLTools(db_manager).get_tools()}


@pytest.fixture
def broken_db_manager(tmp_path) -> DatabaseConnectionManager:
    """A manager pointing at a file that is not a SQLite database."""
    path = tmp_path / "broken.db"
    path.write_bytes(b"this is not a sqlite database" * 32)
    manager = DatabaseConnectionManager(f"sqlite:///{path.as_posix()}")
    try:
        yield manager
    finally:
        manager.close()


# --------------------------------------------------------------------------
# list_tables
# --------------------------------------------------------------------------
def test_list_tables_returns_the_real_tables(tools: dict):
    content = tools["list_tables"].invoke({})

    assert set(json.loads(content)) == {"customers", "orders", "order_items"}


def test_list_tables_rejects_an_empty_schema_name(tools: dict):
    content = tools["list_tables"].invoke({"schema_name": ""})

    assert content == "Schema inspection failed: Invalid schema tool input."


def test_list_tables_reports_a_broken_database(broken_db_manager):
    broken_tools = {tool.name: tool for tool in SQLTools(broken_db_manager).get_tools()}

    content = broken_tools["list_tables"].invoke({})

    assert content.startswith("Schema inspection failed:")
    assert "Could not list database tables." in content


# --------------------------------------------------------------------------
# describe_table
# --------------------------------------------------------------------------
def test_describe_table_returns_columns_and_relationships(tools: dict):
    content = tools["describe_table"].invoke({"table_name": "orders"})

    data = json.loads(content)
    assert data["table_name"] == "orders"
    assert [column["name"] for column in data["columns"]] == [
        "id",
        "customer_id",
        "order_date",
        "status",
        "total",
    ]
    assert data["primary_key"] == ["id"]
    assert data["foreign_keys"][0]["referred_table"] == "customers"


def test_describe_table_reports_a_missing_table(tools: dict):
    content = tools["describe_table"].invoke({"table_name": "does_not_exist"})

    assert content == (
        "Schema inspection failed: Table 'does_not_exist' was not found."
    )


def test_describe_table_rejects_an_empty_table_name(tools: dict):
    content = tools["describe_table"].invoke({"table_name": ""})

    assert content == "Schema inspection failed: Invalid schema tool input."


def test_describe_table_reports_a_broken_database(broken_db_manager):
    broken_tools = {tool.name: tool for tool in SQLTools(broken_db_manager).get_tools()}

    content = broken_tools["describe_table"].invoke({"table_name": "customers"})

    assert content.startswith("Schema inspection failed:")


# --------------------------------------------------------------------------
# execute_sql_query
# --------------------------------------------------------------------------
def test_execute_sql_query_returns_rows_and_columns(tools: dict):
    content = tools["execute_sql_query"].invoke(
        {"query": "SELECT id, name FROM customers ORDER BY id"}
    )

    payload = json.loads(content)
    assert payload["executed_sql"] == "SELECT id, name FROM customers ORDER BY id"
    assert payload["data"]["columns"] == ["id", "name"]
    assert payload["data"]["row_count"] == 4
    assert payload["data"]["truncated"] is False


def test_execute_sql_query_rejects_an_empty_query(tools: dict):
    content = tools["execute_sql_query"].invoke({"query": ""})

    assert content == "Invalid SQL tool input."


def test_execute_sql_query_rejects_write_statements(tools: dict):
    content = tools["execute_sql_query"].invoke({"query": "DELETE FROM customers"})

    assert content == "SQL execution failed: Only SELECT queries are allowed."


def test_execute_sql_query_rejects_blocked_functions(tools: dict):
    content = tools["execute_sql_query"].invoke({"query": "SELECT pg_sleep(10)"})

    assert content == "SQL execution failed: Query uses a forbidden function."


def test_execute_sql_query_reports_execution_failures(tools: dict):
    content = tools["execute_sql_query"].invoke(
        {"query": "SELECT not_a_column FROM customers"}
    )

    assert content.startswith("SQL execution failed:")
    assert "Query failed" in content


def test_execute_sql_query_reports_missing_tables(tools: dict):
    content = tools["execute_sql_query"].invoke(
        {"query": "SELECT * FROM does_not_exist"}
    )

    assert content.startswith("SQL execution failed:")


def test_tool_names_are_stable(tools: dict):
    assert set(tools) == {"list_tables", "describe_table", "execute_sql_query"}
