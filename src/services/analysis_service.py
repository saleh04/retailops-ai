import logging
from typing import Any

from langchain_core.messages import AIMessage, ToolCall, ToolMessage

from agents.sql_agent import SQLAgent
from database.connection import DatabaseConnectionManager
from models.pydantic_schemas.analysis import (
    AnalysisMetadata,
    AnalysisResponse,
    SchemaToolResult,
    SQLExecutionResult,
)

logger = logging.getLogger(__name__)


class AnalysisService:

    def __init__(self, manager: DatabaseConnectionManager):
        self._dialect = manager.database
        self._agent = SQLAgent(manager)
        self.SQL_TOOL = "execute_sql_query"
        self.SCHEMA_TOOLS = {"list_tables", "describe_table"}

    def failure(self, error: str) -> AnalysisResponse:
        return self.build_response(
            status="failed",
            answer=None,
            queries=[],
            schema_results=[],
            tools_used=[],
            error=error,
        )

    @staticmethod
    def collect_tool_trace(messages: list):
        tool_calls = {
            call["id"]: call
            for msg in messages
            if isinstance(msg, AIMessage)
            for call in msg.tool_calls
        }

        tool_messages = {}
        tools_used = []
        for msg in messages:
            if isinstance(msg, ToolMessage) and msg.tool_call_id in tool_calls:
                tool_messages[msg.tool_call_id] = msg
                tools_used.append(tool_calls[msg.tool_call_id]["name"])

        return tool_calls, tool_messages, tools_used

    @staticmethod
    def failed_query(call_id: str, requested_sql: str, error: str) -> SQLExecutionResult:
        return SQLExecutionResult(
            tool_call_id=call_id,
            requested_sql=requested_sql,
            status="failed",
            error=error,
        )

    def parse_sql_call(self, call_id: str, call: ToolCall,
                        tool_message: ToolMessage | None):
        
        requested_sql = call["args"].get("query", "").strip()

        if not requested_sql:
            return None, "SQL tool call contained an invalid query."

        try:
            execution = SQLExecutionResult.model_validate(
                {**tool_message.artifact, "tool_call_id": call_id}
            )
            return execution, None

        except Exception:  # noqa: BLE001
            return (
                self.failed_query(
                    call_id,
                    requested_sql,
                    "Invalid or missing SQL execution artifact.",
                ),
                "Invalid SQL execution trace.",
            )

    @staticmethod
    def failed_schema(call_id: str, tool_name: str, error: str) -> SchemaToolResult:
        return SchemaToolResult(
            tool_call_id=call_id,
            tool_name=tool_name,
            status="failed",
            error=error,
        )

    def parse_schema_call(self, call_id: str, tool_name: str,
                             tool_message: ToolMessage | None):
        try:
            result = SchemaToolResult.model_validate(
                {**tool_message.artifact, "tool_call_id": call_id}
            )
            return result, None

        except Exception:  # noqa: BLE001
            return (
                self.failed_schema(
                    call_id,
                    tool_name,
                    "Invalid or missing schema inspection artifact.",
                ),
                "Invalid schema execution trace.",
            )

    @staticmethod
    def extract_answer(final_message: Any):
        
        if isinstance(final_message, AIMessage) and not final_message.tool_calls:
            return final_message.text.strip() or None

        return None

    @staticmethod
    def resolve_outcome(
        queries: list[SQLExecutionResult],
        schema_results: list[SchemaToolResult],
        answer: str | None,
        trace_error: str | None
    ):
        
        if trace_error is not None:
            return "failed", None, trace_error

        if queries:
            successful = [q for q in queries if q.status == "success"]
            missing_success_error = "No SQL query completed successfully."
            is_empty = all(q.data.row_count == 0 for q in successful)
            empty_answer = "No matching rows were returned."
        else:
            successful = [r for r in schema_results if r.status == "success"]
            missing_success_error = "No database tool completed successfully."
            is_empty = all(not r.data for r in successful)
            empty_answer = "No schema information was found."

        if not successful:
            return "failed", None, missing_success_error

        if not answer:
            return "failed", None, "Agent did not produce a final answer."

        if is_empty:
            return "no_data", empty_answer, None

        return "success", answer, None

    def analyze(self, question: str) -> AnalysisResponse:
        # First Case "Empty Question".
        if not question or not question.strip():
            return self.failure("Question cannot be empty.")

        try:
            state = self._agent.ask(question)
        # Second Case "Agent Failed".
        except Exception:
            logger.exception("Agent execution failed.")
            return self.failure("Agent execution failed.")

        messages = state.get("messages", [])

        # Third Case "No Valid Messages".
        if not messages:
            return self.failure("Agent returned no valid messages.")

        tool_calls, tool_messages, tools_used = self.collect_tool_trace(messages)

        queries = []
        schema_results = []
        trace_error = None

        for call_id, call in tool_calls.items():
            tool_name = call["name"]
            tool_message = tool_messages.get(call_id)

            # Fourth Case "SQL Tool Call".
            if tool_name == self.SQL_TOOL:
                query, error = self.parse_sql_call(call_id, call, tool_message)
                if query is not None:
                    queries.append(query)

            # Fifth Case "Schema Tool Call".
            elif tool_name in self.SCHEMA_TOOLS:
                result, error = self.parse_schema_call(
                    call_id, tool_name, tool_message
                )
                schema_results.append(result)

            if error is not None:
                trace_error = error

        status, answer, error = self.resolve_outcome(
            queries=queries,
            schema_results=schema_results,
            answer=self.extract_answer(messages[-1]),
            trace_error=trace_error,
        )

        return self.build_response(
            status=status,
            answer=answer,
            queries=queries,
            schema_results=schema_results,
            tools_used=tools_used,
            error=error,
        )

    def build_response(self, status: str, answer: str | None,
                        queries: list[SQLExecutionResult],
                        schema_results: list[SchemaToolResult],
                        tools_used: list[str],
                        error: str | None = None) -> AnalysisResponse:
        
        return AnalysisResponse(
            status=status,
            answer=answer,
            queries=queries,
            schema_results=schema_results,
            metadata=AnalysisMetadata(
                dialect=self._dialect,
                tools_used=tools_used
            ),
            error=error,
        )