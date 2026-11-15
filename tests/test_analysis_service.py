"""Regression tests for the analysis service (`services.analysis_service`).

Only the LLM provider is replaced by a deterministic scripted model.  The
agent graph, the SQL tools, the validator, the executor and the SQLite
database all run for real.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from database.connection import DatabaseConnectionManager
from services.analysis_service import AnalysisService


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def tool_call(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


def tool_result(call_id: str, artifact: object) -> ToolMessage:
    return ToolMessage(content="{}", tool_call_id=call_id, artifact=artifact)


SUCCESS_SQL_ARTIFACT = {
    "requested_sql": "SELECT COUNT(*) AS c FROM customers",
    "executed_sql": "SELECT COUNT(*) AS c FROM customers",
    "status": "success",
    "data": {
        "columns": ["c"],
        "rows": [{"c": 4}],
        "row_count": 1,
        "truncated": False,
    },
    "error": None,
}


class StubAgent:
    """Replaces `SQLAgent` to exercise the trace parsing in isolation."""

    def __init__(self, messages=None, error=None):
        self._messages = messages or []
        self._error = error
        self.calls: list[tuple[str, list | None]] = []

    def ask(self, question: str, history: list | None = None):
        self.calls.append((question, history))
        if self._error is not None:
            raise self._error
        return {"messages": self._messages}


@pytest.fixture
def service(db_manager: DatabaseConnectionManager, fake_llm) -> AnalysisService:
    fake_llm.install([AIMessage(content="unused")])
    return AnalysisService(db_manager)


def with_agent(service: AnalysisService, agent: StubAgent) -> AnalysisService:
    service._agent = agent
    return service


# --------------------------------------------------------------------------
# Successful SQL backed analysis
# --------------------------------------------------------------------------
def test_successful_analysis_returns_a_grounded_answer(
    fake_llm, db_manager: DatabaseConnectionManager
):
    fake_llm.install(
        [
            tool_call(
                "execute_sql_query",
                {"query": "SELECT COUNT(*) AS c FROM customers"},
                "call_1",
            ),
            AIMessage(content="There are 4 customers in the database."),
        ]
    )

    response = AnalysisService(db_manager).analyze("How many customers are there?")

    assert response.status == "success"
    assert response.answer == "There are 4 customers in the database."
    assert response.error is None
    assert response.metadata.dialect == "sqlite"
    assert response.metadata.tools_used == ["execute_sql_query"]

    assert len(response.queries) == 1
    query = response.queries[0]
    assert query.tool_call_id == "call_1"
    assert query.status == "success"
    assert query.requested_sql == "SELECT COUNT(*) AS c FROM customers"
    assert query.executed_sql == "SELECT COUNT(*) AS c FROM customers"
    assert query.data is not None
    assert query.data.columns == ["c"]
    assert query.data.rows == [{"c": 4}]
    assert query.data.row_count == 1
    assert query.data.total_rows == 1
    assert query.data.truncated is False


def test_analysis_uses_the_real_database_content(
    fake_llm, db_manager: DatabaseConnectionManager
):
    fake_llm.install(
        [
            tool_call(
                "execute_sql_query",
                {"query": "SELECT name FROM customers ORDER BY id"},
                "call_1",
            ),
            AIMessage(content="The customers are listed."),
        ]
    )

    response = AnalysisService(db_manager).analyze("Who are the customers?")

    names = [row["name"] for row in response.queries[0].data.rows]
    assert names == ["Alice", "Bob", "Carla", "Dan"]


def test_analysis_reports_truncated_result_sets(
    fake_llm, db_manager: DatabaseConnectionManager, monkeypatch
):
    from core.config import get_settings

    monkeypatch.setattr(get_settings(), "SQL_MAX_ROWS", 2)

    fake_llm.install(
        [
            tool_call(
                "execute_sql_query",
                {"query": "SELECT id FROM customers ORDER BY id"},
                "call_1",
            ),
            AIMessage(content="Truncated."),
        ]
    )

    response = AnalysisService(db_manager).analyze("List every customer id")

    assert response.queries[0].data.truncated is True
    assert response.queries[0].data.row_count == 2


# --------------------------------------------------------------------------
# Schema only analysis
# --------------------------------------------------------------------------
def test_schema_only_analysis_does_not_execute_data_queries(
    fake_llm, db_manager: DatabaseConnectionManager
):
    fake_llm.install(
        [
            tool_call("list_tables", {}, "call_1"),
            AIMessage(content="The database contains three tables."),
        ]
    )

    response = AnalysisService(db_manager).analyze("Which tables exist?")

    assert response.status == "success"
    assert response.answer == "The database contains three tables."
    assert response.queries == []
    assert len(response.schema_results) == 1

    schema_result = response.schema_results[0]
    assert schema_result.tool_name == "list_tables"
    assert schema_result.status == "success"
    assert set(schema_result.data) == {"customers", "orders", "order_items"}
    assert response.metadata.tools_used == ["list_tables"]


def test_describe_table_analysis_returns_column_metadata(
    fake_llm, db_manager: DatabaseConnectionManager
):
    fake_llm.install(
        [
            tool_call("describe_table", {"table_name": "orders"}, "call_1"),
            AIMessage(content="Orders has five columns."),
        ]
    )

    response = AnalysisService(db_manager).analyze("Describe the orders table")

    assert response.status == "success"
    assert response.queries == []

    schema_result = response.schema_results[0]
    assert schema_result.tool_name == "describe_table"
    assert schema_result.data["table_name"] == "orders"
    assert [column["name"] for column in schema_result.data["columns"]] == [
        "id",
        "customer_id",
        "order_date",
        "status",
        "total",
    ]
    assert schema_result.data["primary_key"] == ["id"]
    assert schema_result.data["foreign_keys"][0]["referred_table"] == "customers"


# --------------------------------------------------------------------------
# Empty result sets
# --------------------------------------------------------------------------
def test_zero_row_result_is_reported_as_no_data(
    fake_llm, db_manager: DatabaseConnectionManager
):
    fake_llm.install(
        [
            tool_call(
                "execute_sql_query",
                {"query": "SELECT id FROM customers WHERE id = 9999"},
                "call_1",
            ),
            AIMessage(content="I found nothing."),
        ]
    )

    response = AnalysisService(db_manager).analyze("Which customer has id 9999?")

    assert response.status == "no_data"
    assert response.answer == "No matching rows were returned."
    assert response.error is None
    assert response.queries[0].status == "success"
    assert response.queries[0].data.row_count == 0


# --------------------------------------------------------------------------
# Error recovery
# --------------------------------------------------------------------------
def test_agent_recovers_from_a_failing_sql_call(
    fake_llm, db_manager: DatabaseConnectionManager
):
    fake_llm.install(
        [
            tool_call(
                "execute_sql_query",
                {"query": "SELECT not_a_column FROM customers"},
                "call_1",
            ),
            tool_call(
                "execute_sql_query",
                {"query": "SELECT COUNT(*) AS c FROM customers"},
                "call_2",
            ),
            AIMessage(content="After correcting the query: there are 4 customers."),
        ]
    )

    response = AnalysisService(db_manager).analyze("How many customers are there?")

    assert response.status == "success"
    assert response.answer == "After correcting the query: there are 4 customers."

    assert len(response.queries) == 2
    failed, succeeded = response.queries

    assert failed.tool_call_id == "call_1"
    assert failed.status == "failed"
    assert failed.error is not None
    assert failed.data is None

    assert succeeded.tool_call_id == "call_2"
    assert succeeded.status == "success"
    assert succeeded.data.rows == [{"c": 4}]


def test_failed_query_alone_results_in_a_failed_analysis(
    fake_llm, db_manager: DatabaseConnectionManager
):
    fake_llm.install(
        [
            tool_call(
                "execute_sql_query",
                {"query": "SELECT not_a_column FROM customers"},
                "call_1",
            ),
            AIMessage(content="That did not work."),
        ]
    )

    response = AnalysisService(db_manager).analyze("How many customers are there?")

    assert response.status == "failed"
    assert response.answer is None
    assert response.error == "No SQL query completed successfully."
    assert response.queries[0].status == "failed"


def test_agent_failure_is_reported_as_failed(service: AnalysisService):
    agent = StubAgent(error=RuntimeError("boom"))
    with_agent(service, agent)

    response = service.analyze("How many customers are there?")

    assert response.status == "failed"
    assert response.error == "boom"
    assert response.answer is None


def test_unexpected_agent_exception_is_handled(service: AnalysisService):
    with_agent(service, StubAgent(error=ValueError("unexpected")))

    response = service.analyze("How many customers are there?")

    assert response.status == "failed"
    assert response.error == "Agent execution failed."


def test_agent_without_messages_is_reported(service: AnalysisService):
    with_agent(service, StubAgent(messages=[]))

    response = service.analyze("How many customers are there?")

    assert response.status == "failed"
    assert response.error == "Agent returned no valid messages."


# --------------------------------------------------------------------------
# Broken tool artefacts
# --------------------------------------------------------------------------
def test_missing_tool_artifact_is_reported(service: AnalysisService):
    messages = [
        tool_call("execute_sql_query", {"query": "SELECT 1 FROM customers"}, "call_1"),
        tool_result("call_1", None),
        AIMessage(content="Done."),
    ]
    with_agent(service, StubAgent(messages=messages))

    response = service.analyze("How many customers are there?")

    assert response.status == "failed"
    assert response.error == "Invalid SQL execution trace."
    assert response.queries[0].status == "failed"
    assert response.queries[0].error == "Invalid or missing SQL execution artifact."


def test_non_dict_tool_artifact_is_reported(service: AnalysisService):
    messages = [
        tool_call("execute_sql_query", {"query": "SELECT 1 FROM customers"}, "call_1"),
        tool_result("call_1", "not-a-dict"),
        AIMessage(content="Done."),
    ]
    with_agent(service, StubAgent(messages=messages))

    response = service.analyze("How many customers are there?")

    assert response.status == "failed"
    assert response.error == "Invalid SQL execution trace."


def test_incomplete_tool_artifact_is_reported(service: AnalysisService):
    messages = [
        tool_call("execute_sql_query", {"query": "SELECT 1 FROM customers"}, "call_1"),
        tool_result("call_1", {"status": "success"}),
        AIMessage(content="Done."),
    ]
    with_agent(service, StubAgent(messages=messages))

    response = service.analyze("How many customers are there?")

    assert response.status == "failed"
    assert response.error == "Invalid SQL execution trace."


def test_missing_schema_artifact_is_reported(service: AnalysisService):
    messages = [
        tool_call("list_tables", {}, "call_1"),
        tool_result("call_1", None),
        AIMessage(content="Done."),
    ]
    with_agent(service, StubAgent(messages=messages))

    response = service.analyze("Which tables exist?")

    assert response.status == "failed"
    assert response.error == "Invalid schema execution trace."
    assert response.schema_results[0].status == "failed"
    assert response.schema_results[0].error == (
        "Invalid or missing schema inspection artifact."
    )


def test_incomplete_schema_artifact_is_reported(service: AnalysisService):
    messages = [
        tool_call("list_tables", {}, "call_1"),
        tool_result("call_1", {"status": "success"}),
        AIMessage(content="Done."),
    ]
    with_agent(service, StubAgent(messages=messages))

    response = service.analyze("Which tables exist?")

    assert response.status == "failed"
    assert response.error == "Invalid schema execution trace."
    assert response.schema_results[0].error == (
        "Invalid or missing schema inspection artifact."
    )


def test_sql_call_without_a_query_is_rejected(service: AnalysisService):
    messages = [
        tool_call("execute_sql_query", {}, "call_1"),
        tool_result("call_1", SUCCESS_SQL_ARTIFACT),
        AIMessage(content="Done."),
    ]
    with_agent(service, StubAgent(messages=messages))

    response = service.analyze("How many customers are there?")

    assert response.status == "failed"
    assert response.error == "SQL tool call contained an invalid query."
    assert response.queries == []


def test_missing_final_answer_is_reported(service: AnalysisService):
    messages = [
        tool_call(
            "execute_sql_query",
            {"query": "SELECT COUNT(*) AS c FROM customers"},
            "call_1",
        ),
        tool_result("call_1", SUCCESS_SQL_ARTIFACT),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "execute_sql_query",
                    "args": {"query": "SELECT COUNT(*) AS c FROM customers"},
                    "id": "call_2",
                    "type": "tool_call",
                }
            ],
        ),
        tool_result("call_2", SUCCESS_SQL_ARTIFACT),
    ]
    with_agent(service, StubAgent(messages=messages))

    response = service.analyze("How many customers are there?")

    assert response.status == "failed"
    assert response.error == "Agent did not produce a final answer."


# --------------------------------------------------------------------------
# Input validation
# --------------------------------------------------------------------------
@pytest.mark.parametrize("question", ["", "   ", "\n\t ", None])
def test_empty_question_is_rejected(service: AnalysisService, question):
    response = service.analyze(question)

    assert response.status == "failed"
    assert response.error == "Question cannot be empty."
    assert response.answer is None
    assert response.queries == []
    assert response.schema_results == []


def test_only_the_current_turn_is_analysed(service: AnalysisService):
    """Tool calls of previous turns must not be attributed to this turn."""
    messages = [
        HumanMessage(content="older question"),
        tool_call(
            "execute_sql_query",
            {"query": "SELECT id FROM customers"},
            "old_call",
        ),
        tool_result("old_call", SUCCESS_SQL_ARTIFACT),
        HumanMessage(content="current question"),
        tool_call(
            "execute_sql_query",
            {"query": "SELECT COUNT(*) AS c FROM customers"},
            "new_call",
        ),
        tool_result("new_call", SUCCESS_SQL_ARTIFACT),
        AIMessage(content="There are 4 customers."),
    ]
    with_agent(service, StubAgent(messages=messages))

    response = service.analyze(
        "current question", history=[{"role": "user", "content": "older question"}]
    )

    assert response.status == "success"
    assert len(response.queries) == 1
    assert response.queries[0].tool_call_id == "new_call"
    assert response.metadata.tools_used == ["execute_sql_query"]


def test_history_is_forwarded_to_the_agent(service: AnalysisService):
    agent = StubAgent(messages=[AIMessage(content="ok")])
    with_agent(service, agent)

    history = [{"role": "user", "content": "previous question"}]
    service.analyze("follow up question", history=history)

    assert agent.calls == [("follow up question", history)]


# --------------------------------------------------------------------------
# Agent level guards
# --------------------------------------------------------------------------
def test_agent_rejects_an_empty_question(fake_llm, db_manager: DatabaseConnectionManager):
    from agents.sql_agent import SQLAgent

    fake_llm.install([AIMessage(content="unused")])
    agent = SQLAgent(db_manager)

    with pytest.raises(ValueError, match="Question cannot be empty."):
        agent.ask("   ")


def test_agent_recursion_limit_is_reported_as_a_failure(
    fake_llm, db_manager: DatabaseConnectionManager
):
    """A model that keeps calling tools must not loop forever."""
    fake_llm.install_with_unique_tool_call_ids(
        [
            tool_call(
                "execute_sql_query",
                {"query": "SELECT id FROM customers"},
                "call_1",
            )
        ]
    )

    response = AnalysisService(db_manager).analyze("How many customers are there?")

    assert response.status == "failed"
    assert response.error == "Agent exceeded the maximum recursion limit."
    assert response.answer is None
