from langchain.agents import create_agent
from langgraph.errors import GraphRecursionError

from agents.llm.llm_factory import LLMFactory
from agents.prompts.sql_agent_prompt import SQL_AGENT_SYSTEM_PROMPT
from agents.tools.sql_tools import SQLTools
from core.config import get_settings
from database.connection import DatabaseConnectionManager


class SQLAgent:

    def __init__(self, manager: DatabaseConnectionManager):
        settings = get_settings()
        self._recursion_limit = settings.AGENT_RECURSION_LIMIT

        model = LLMFactory(config=settings).create()
        tools = SQLTools(manager).get_tools()

        system_prompt = SQL_AGENT_SYSTEM_PROMPT.substitute(
            dialect=manager.database,
            max_rows=settings.SQL_MAX_ROWS,
        )

        self.agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
        )

    def ask(self, question: str, history: list[dict] | None = None):

        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question cannot be empty.")

        try:
            result = self.agent.invoke(
                {
                    "messages": [
                        *(history or []),
                        {"role": "user", "content": question},
                    ]
                },
                config={"recursion_limit": self._recursion_limit},
            )
        except GraphRecursionError as exc:
            raise RuntimeError(
                "Agent exceeded the maximum recursion limit."
            ) from exc

        return result
