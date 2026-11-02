from langchain.agents import create_agent

from agents.llm.llm_factory import LLMFactory
from agents.prompts.sql_agent_prompt import SQL_AGENT_SYSTEM_PROMPT
from agents.tools.sql_tools import SQLTools
from core.config import get_settings
from database.connection import DatabaseConnectionManager


class SQLAgent:

    def __init__(self, manager: DatabaseConnectionManager):

        model = LLMFactory(config=get_settings()).create()
        tools = SQLTools(manager).get_tools()

        system_prompt = SQL_AGENT_SYSTEM_PROMPT.format(
            dialect=manager.database
        )

        self.agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
        )

    def ask(self, question: str) -> str:

        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question cannot be empty.")

        result = self.agent.invoke({
            "messages": [
                {"role": "user", "content": question}
            ]
        })

        return str(result["messages"][-1].text)
