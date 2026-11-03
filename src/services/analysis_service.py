import logging

from langchain_core.messages import AIMessage, ToolMessage
from pydantic import ValidationError

from agents.sql_agent import SQLAgent
from database.connection import DatabaseConnectionManager
from models.pydantic_schemas.analysis import (
    AnalysisMetadata,
    AnalysisResponse,
    SQLExecutionResult,
)

logger = logging.getLogger(__name__)

class AnalysisService:

    def __init__(self, manager: DatabaseConnectionManager, agent: SQLAgent | None = None):
        
        self._dialect = manager.database
        self._agent = agent if agent is not None else SQLAgent(manager)
        
    @staticmethod
    def _failed_query(call_id: str, requested_sql: str, error: str) -> SQLExecutionResult:

        return SQLExecutionResult(
            tool_call_id=call_id,
            requested_sql=requested_sql,
            executed_sql=None,
            status="failed",
            data=None,
            error=error,
        )

    def _build_response(self, status: str, answer: str | None,
                                queries: list[SQLExecutionResult],
                                tools_used: list[str],
                                error: str | None = None,) -> AnalysisResponse:

        return AnalysisResponse(
            status=status,
            answer=answer,
            queries=queries,
            metadata=AnalysisMetadata(
                dialect=self._dialect,
                tools_used=tools_used,
            ),
            error=error,
        )

    def analyze(self, question: str) -> AnalysisResponse:

        # First Case "Empty Question".
        if not isinstance(question, str) or not question.strip():
            return self._build_response(
                status="failed",
                answer=None,
                queries=[],
                tools_used=[],
                error="Question cannot be empty.",
            )

        try:
            state = self._agent.ask(question)
            
        # Second Case "Agent Failed"
        except Exception:
            logger.exception("Agent execution failed.")

            return self._build_response(
                status="failed",
                answer=None,
                queries=[],
                tools_used=[],
                error="Agent execution failed.",
            )

        messages = state.get("messages") if isinstance(state, dict) else None

        # Third Case "Invalid or Empty Messages".
        if not isinstance(messages, list) or not messages:
            return self._build_response(
                status="failed",
                answer=None,
                queries=[],
                tools_used=[],
                error="Agent returned no valid messages.",
            )

        tool_calls = {}
        for message in messages:
            if isinstance(message, AIMessage):
                for call in message.tool_calls:
                    call_id = call.get("id")
                    tool_calls[call_id] = call

        tool_messages = {}
        tools_used = []
        for message in messages:
            if isinstance(message, ToolMessage):
                call = tool_calls.get(message.tool_call_id)
                
                if call is None:
                    continue

                tool_messages[message.tool_call_id] = message
                tools_used.append(call["name"])

        queries = []
        trace_error = None
        for call_id, call in tool_calls.items():

            if call["name"] != "execute_sql_query":
                continue

            requested_sql = call.get("args", {}).get("query")

            tool_message = tool_messages.get(call_id)

            if tool_message is None:
                queries.append(self._failed_query(
                        call_id,
                        requested_sql,
                        "SQL tool result is missing.",
                    )
                )
                trace_error = "Incomplete SQL execution trace."
                continue

            artifact = tool_message.artifact
            if not isinstance(artifact, dict):
                queries.append(self._failed_query(
                        call_id,
                        requested_sql,
                        "SQL execution artifact is missing.",
                    )
                )
                trace_error = "Incomplete SQL execution trace."
                continue

            
            try:
                execution = SQLExecutionResult.model_validate({
                    **artifact,
                    "tool_call_id": call_id,
                })

                if execution.requested_sql.strip() != requested_sql.strip():
                    raise ValueError("SQL tool call does not match artifact.")

            except (ValidationError, ValueError):
                queries.append(
                    self._failed_query(
                        call_id,
                        requested_sql,
                        "Invalid SQL execution artifact.",
                    )
                )
                trace_error = "Invalid SQL execution trace."
                continue

            queries.append(execution)

        final_message = messages[-1]
        answer = None
        if isinstance(final_message, AIMessage) and not final_message.tool_calls:
            text = final_message.text

            if isinstance(text, str) and text.strip():
                answer = text.strip()

        successful_queries = [
            query for query in queries
            if query.status == "success"
        ]

        # Fourth Case "Incomplete SQL Execution Trace".
        if trace_error is not None:
            return self._build_response(
                status="failed",
                answer=None,
                queries=queries,
                tools_used=tools_used,
                error=trace_error,
            )

        # Fifth Case "No Successful SQL Queries".
        if not successful_queries:
            return self._build_response(
                status="failed",
                answer=None,
                queries=queries,
                tools_used=tools_used,
                error="No SQL query completed successfully.",
            )

        # Sixth Case "Missing Final Answer".
        if not answer:
            return self._build_response(
                status="failed",
                answer=None,
                queries=queries,
                tools_used=tools_used,
                error="Agent did not produce a final answer.",
            )

        # Seventh Case "No Matching Rows".
        if all(
            query.data.row_count == 0
            for query in successful_queries
        ):
            return self._build_response(
                status="no_data",
                answer="No matching rows were returned.",
                queries=queries,
                tools_used=tools_used,
            )

        # Eighth Case "Successful Analysis".
        return self._build_response(
            status="success",
            answer=answer,
            queries=queries,
            tools_used=tools_used,
        )

