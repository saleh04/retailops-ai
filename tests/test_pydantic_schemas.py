"""Contract tests for the pydantic schemas and the settings model.

These objects form the public contract of the API: invalid combinations must
be rejected with a helpful message instead of silently producing a broken
response.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.config import Settings
from models.pydantic_schemas.agent_tool_inputs import DatabaseToolInput
from models.pydantic_schemas.analysis import (
    QueryData,
    SchemaToolResult,
    SQLExecutionResult,
)
from models.pydantic_schemas.requests import ConnectionRequest


# --------------------------------------------------------------------------
# SQLExecutionResult
# --------------------------------------------------------------------------
def _valid_data() -> QueryData:
    return QueryData(columns=["c"], rows=[{"c": 1}], row_count=1, truncated=False)


def test_successful_execution_requires_sql_and_data():
    execution = SQLExecutionResult(
        tool_call_id="call_1",
        requested_sql="SELECT 1",
        executed_sql="SELECT 1",
        status="success",
        data=_valid_data(),
    )

    assert execution.status == "success"
    assert execution.error is None


def test_successful_execution_cannot_carry_an_error():
    with pytest.raises(ValidationError, match="Successful execution cannot contain an error"):
        SQLExecutionResult(
            tool_call_id="call_1",
            requested_sql="SELECT 1",
            executed_sql="SELECT 1",
            status="success",
            data=_valid_data(),
            error="boom",
        )


def test_successful_execution_requires_the_executed_sql():
    with pytest.raises(ValidationError, match="Successful execution requires SQL and data"):
        SQLExecutionResult(
            tool_call_id="call_1",
            requested_sql="SELECT 1",
            status="success",
            data=_valid_data(),
        )


def test_failed_execution_cannot_carry_data():
    with pytest.raises(ValidationError, match="Failed execution cannot contain data"):
        SQLExecutionResult(
            tool_call_id="call_1",
            requested_sql="SELECT 1",
            status="failed",
            data=_valid_data(),
            error="boom",
        )


def test_failed_execution_requires_an_error_message():
    with pytest.raises(ValidationError, match="Failed execution requires an error message"):
        SQLExecutionResult(
            tool_call_id="call_1",
            requested_sql="SELECT 1",
            status="failed",
        )


def test_execution_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        SQLExecutionResult(
            tool_call_id="call_1",
            requested_sql="SELECT 1",
            status="failed",
            error="boom",
            unexpected="value",
        )


# --------------------------------------------------------------------------
# SchemaToolResult
# --------------------------------------------------------------------------
def test_successful_schema_result_requires_data():
    with pytest.raises(ValidationError, match="Successful schema inspection requires data"):
        SchemaToolResult(
            tool_call_id="call_1",
            tool_name="list_tables",
            status="success",
        )


def test_failed_schema_result_requires_an_error_message():
    with pytest.raises(ValidationError, match="Failed schema inspection requires an error message"):
        SchemaToolResult(
            tool_call_id="call_1",
            tool_name="list_tables",
            status="failed",
        )


def test_schema_result_rejects_an_unknown_tool_name():
    with pytest.raises(ValidationError):
        SchemaToolResult(
            tool_call_id="call_1",
            tool_name="drop_everything",
            status="success",
            data=["customers"],
        )


# --------------------------------------------------------------------------
# DatabaseToolInput
# --------------------------------------------------------------------------
def test_tool_input_rejects_a_query_combined_with_a_table_name():
    with pytest.raises(ValidationError, match="cannot be combined"):
        DatabaseToolInput(query="SELECT 1", table_name="customers")


def test_tool_input_rejects_an_empty_query():
    with pytest.raises(ValidationError):
        DatabaseToolInput(query="   ")


def test_tool_input_rejects_an_empty_table_name():
    with pytest.raises(ValidationError):
        DatabaseToolInput(table_name="")


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------
def test_connection_request_rejects_an_empty_url():
    with pytest.raises(ValidationError, match="Database URL cannot be empty"):
        ConnectionRequest(database_url="   ")


def test_connection_request_hides_the_url_in_repr():
    request = ConnectionRequest(database_url="postgresql://user:secret@host/db")

    assert "secret" not in repr(request)


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
def _settings(**overrides) -> Settings:
    values = {
        "APP_NAME": "test-app",
        "APP_VERSION": "0.0.0",
        "POOL_PRE_PING": True,
        "CONNECT_TIMEOUT": 10,
        "POSTGRES_USERNAME": "postgres",
        "POSTGRES_PASSWORD": "secret",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": 5432,
        "POSTGRES_MAIN_DATABASE": "test",
    }
    values.update(overrides)
    return Settings(**values)


def test_cors_origins_are_parsed_from_a_comma_separated_string():
    assert _settings(CORS_ORIGINS="http://a.test, http://b.test").CORS_ORIGINS == [
        "http://a.test",
        "http://b.test",
    ]


def test_cors_origins_fall_back_to_wildcard():
    assert _settings(CORS_ORIGINS=" , ").CORS_ORIGINS == ["*"]


def test_cors_origins_accept_a_list():
    assert _settings(CORS_ORIGINS=["http://a.test"]).CORS_ORIGINS == [
        "http://a.test"
    ]


@pytest.mark.parametrize(
    "field", ["OPENAI_API_KEY", "OPENAI_API_URL", "GOOGLE_API_KEY", "MODEL_ID"]
)
def test_blank_optional_values_become_none(field: str):
    settings = _settings(**{field: "   "})

    assert getattr(settings, field) is None


def test_default_temperatures_and_limits_are_validated():
    with pytest.raises(ValidationError):
        _settings(DEFAULT_TEMPERATURE=-1.0)

    with pytest.raises(ValidationError):
        _settings(DEFAULT_MAX_TOKENS=0)
