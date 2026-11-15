from langchain_core.messages import AIMessage

from agents import sql_agent
from agents.sql_agent import SQLAgent
from core.config import get_settings


def test_agent_substitutes_prompt_runtime_values(
    fake_llm, db_manager, monkeypatch
):
    captured = {}

    def capture_agent(*, model, tools, system_prompt):
        captured["system_prompt"] = system_prompt
        return object()

    monkeypatch.setattr(sql_agent, "create_agent", capture_agent)
    monkeypatch.setattr(get_settings(), "SQL_MAX_ROWS", 17)
    fake_llm.install([AIMessage(content="unused")])

    SQLAgent(db_manager)

    assert "Database dialect: sqlite." in captured["system_prompt"]
    assert "LIMIT of at most 17." in captured["system_prompt"]
