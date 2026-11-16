"""End-to-end regression tests for the FastAPI application.

The complete workflow is exercised against the real application:

    connect -> inspect schema -> ask -> follow up -> history -> delete
    -> disconnect

Only the LLM provider is replaced by a deterministic scripted model, the
external SQLite database and the internal PostgreSQL store are real.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from sqlalchemy import text

from main import app
from agents.llm.llm_factory import LLMFactory
from database.connection import DatabaseConnectionManager


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def tool_call(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


@pytest_asyncio.fixture
async def api_client(internal_store: None):
    """An HTTP client bound to the application with a clean internal store."""
    async with app.router.lifespan_context(app):
        async with app.state.db_engine.begin() as connection:
            await connection.execute(
                text("TRUNCATE TABLE message, conversation, connection_record CASCADE")
            )

        app.state.db_manager = None
        app.state.connection_id = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client

        manager = app.state.db_manager
        if manager is not None:
            manager.close()
        app.state.db_manager = None
        app.state.connection_id = None


@pytest_asyncio.fixture
async def connected_client(api_client: AsyncClient, sample_db_path: str):
    """A client with an active connection to the sample SQLite database."""
    response = await api_client.post(
        "/api/v1/connections",
        json={"database_url": f"sqlite:///{sample_db_path}"},
    )
    assert response.status_code == 201
    return api_client


# --------------------------------------------------------------------------
# Connection lifecycle
# --------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.asyncio
async def test_connection_status_starts_as_disconnected(api_client: AsyncClient):
    response = await api_client.get("/api/v1/connections")

    assert response.status_code == 200
    assert response.json()["status"] == "disconnected"
    assert response.json()["connection_id"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_connect_external_database(api_client: AsyncClient, sample_db_path: str):
    response = await api_client.post(
        "/api/v1/connections",
        json={"database_url": f"sqlite:///{sample_db_path}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "connected"
    assert body["dialect"] == "sqlite"
    assert body["connection_id"] is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_connecting_twice_is_rejected(connected_client: AsyncClient, sample_db_path: str):
    response = await connected_client.post(
        "/api/v1/connections",
        json={"database_url": f"sqlite:///{sample_db_path}"},
    )

    assert response.status_code == 409


@pytest.mark.integration
@pytest.mark.asyncio
async def test_connect_with_an_invalid_url_is_rejected(api_client: AsyncClient):
    response = await api_client.post(
        "/api/v1/connections",
        json={"database_url": "not-a-database-url"},
    )

    assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
async def test_disconnect_releases_the_connection(
    connected_client: AsyncClient, sample_db_path: str
):
    response = await connected_client.delete("/api/v1/connections")

    assert response.status_code == 204

    status = await connected_client.get("/api/v1/connections")
    assert status.json()["status"] == "disconnected"

    schema = await connected_client.get("/api/v1/schema/tables")
    assert schema.status_code == 409


@pytest.mark.integration
@pytest.mark.asyncio
async def test_disconnect_without_connection_is_rejected(api_client: AsyncClient):
    response = await api_client.delete("/api/v1/connections")

    assert response.status_code == 409


# --------------------------------------------------------------------------
# Schema inspection
# --------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.asyncio
async def test_schema_tables_endpoint(connected_client: AsyncClient):
    response = await connected_client.get("/api/v1/schema/tables")

    assert response.status_code == 200
    assert set(response.json()["tables"]) == {"customers", "orders", "order_items"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_schema_tables_with_an_unknown_schema_is_reported(
    connected_client: AsyncClient,
):
    response = await connected_client.get(
        "/api/v1/schema/tables?schema_name=does_not_exist"
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Could not retrieve database tables."


@pytest.mark.integration
@pytest.mark.asyncio
async def test_schema_table_detail_endpoint(connected_client: AsyncClient):
    response = await connected_client.get("/api/v1/schema/tables/orders")

    assert response.status_code == 200
    body = response.json()
    assert body["table_name"] == "orders"
    assert [column["name"] for column in body["columns"]] == [
        "id",
        "customer_id",
        "order_date",
        "status",
        "total",
    ]
    assert body["primary_key"] == ["id"]
    assert body["foreign_keys"][0]["referred_table"] == "customers"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_schema_table_detail_for_unknown_table(connected_client: AsyncClient):
    response = await connected_client.get("/api/v1/schema/tables/does_not_exist")

    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_schema_endpoint_requires_a_connection(api_client: AsyncClient):
    response = await api_client.get("/api/v1/schema/tables")

    assert response.status_code == 409


# --------------------------------------------------------------------------
# Full analysis workflow
# --------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_conversation_workflow(
    connected_client: AsyncClient, fake_llm
):
    fake_llm.install(
        [
            tool_call(
                "execute_sql_query",
                {"query": "SELECT COUNT(*) AS c FROM customers"},
                "call_1",
            ),
            AIMessage(content="There are 4 customers."),
        ],
        [
            tool_call(
                "execute_sql_query",
                {"query": "SELECT name FROM customers WHERE city = 'Berlin' ORDER BY id"},
                "call_2",
            ),
            AIMessage(content="Alice and Carla live in Berlin."),
        ],
    )

    # 1. the first question creates a conversation
    first = await connected_client.post(
        "/api/v1/analysis",
        json={"question": "How many customers are there?"},
    )

    assert first.status_code == 200
    first_body = first.json()
    assert first_body["status"] == "success"
    assert first_body["answer"] == "There are 4 customers."
    assert first_body["metadata"]["dialect"] == "sqlite"
    assert first_body["metadata"]["tools_used"] == ["execute_sql_query"]
    assert first_body["queries"][0]["executed_sql"] == (
        "SELECT COUNT(*) AS c FROM customers"
    )
    assert first_body["queries"][0]["data"]["rows"] == [{"c": 4}]
    assert first_body["queries"][0]["data"]["total_rows"] == 1

    conversation_id = first_body["conversation_id"]
    assert conversation_id is not None

    # 2. the follow up question reuses the conversation
    second = await connected_client.post(
        "/api/v1/analysis",
        json={
            "question": "Which customers live in Berlin?",
            "conversation_id": conversation_id,
        },
    )

    assert second.status_code == 200
    second_body = second.json()
    assert second_body["status"] == "success"
    assert second_body["answer"] == "Alice and Carla live in Berlin."
    assert second_body["conversation_id"] == conversation_id

    # the agent received the previous turn as history
    follow_up_prompt = fake_llm.models[1].calls[0]
    assert any(
        "How many customers are there?" in str(message.content)
        for message in follow_up_prompt
    )

    # 3. the conversation history is persisted
    history = await connected_client.get(f"/api/v1/conversations/{conversation_id}")

    assert history.status_code == 200
    history_body = history.json()
    assert history_body["id"] == conversation_id
    assert history_body["message_count"] == 4

    roles = [message["role"] for message in history_body["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]

    assistant_messages = [
        message for message in history_body["messages"] if message["role"] == "assistant"
    ]
    assert assistant_messages[0]["status"] == "success"
    assert assistant_messages[0]["content"] == "There are 4 customers."
    assert assistant_messages[0]["queries"][0]["executed_sql"] == (
        "SELECT COUNT(*) AS c FROM customers"
    )
    assert assistant_messages[0]["queries"][0]["data"]["rows"] == [{"c": 4}]
    assert assistant_messages[1]["queries"][0]["executed_sql"] == (
        "SELECT name FROM customers WHERE city = 'Berlin' ORDER BY id"
    )

    # 4. the conversation can be listed
    listing = await connected_client.get("/api/v1/conversations")
    assert listing.status_code == 200
    assert any(item["id"] == conversation_id for item in listing.json())

    # 5. deleting the conversation removes it
    deleted = await connected_client.delete(f"/api/v1/conversations/{conversation_id}")
    assert deleted.status_code == 204

    missing = await connected_client.get(f"/api/v1/conversations/{conversation_id}")
    assert missing.status_code == 404

    # 6. disconnecting cleans the state up
    disconnected = await connected_client.delete("/api/v1/connections")
    assert disconnected.status_code == 204

    status = await connected_client.get("/api/v1/connections")
    assert status.json()["status"] == "disconnected"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_analysis_without_a_connection_is_rejected(api_client: AsyncClient):
    response = await api_client.post(
        "/api/v1/analysis",
        json={"question": "How many customers are there?"},
    )

    assert response.status_code == 409


@pytest.mark.integration
@pytest.mark.asyncio
async def test_analysis_with_an_empty_question_is_rejected(connected_client: AsyncClient):
    response = await connected_client.post(
        "/api/v1/analysis",
        json={"question": "   "},
    )

    assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_analysis_with_an_unknown_conversation_is_rejected(
    connected_client: AsyncClient, fake_llm
):
    fake_llm.install([AIMessage(content="unused")])

    response = await connected_client.post(
        "/api/v1/analysis",
        json={
            "question": "How many customers are there?",
            "conversation_id": "00000000-0000-0000-0000-000000000000",
        },
    )

    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failed_analysis_is_reported_with_a_500(
    connected_client: AsyncClient, fake_llm
):
    """A failed analysis must not look like a successful request."""
    fake_llm.install([AIMessage(content="I cannot answer that.")])

    response = await connected_client.post(
        "/api/v1/analysis",
        json={"question": "How many customers are there?"},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["status"] == "failed"
    assert body["answer"] is None
    assert body["error"] == "No database tool completed successfully."
    assert body["conversation_id"] is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_data_analysis_is_reported_with_a_200(
    connected_client: AsyncClient, fake_llm
):
    """An empty result is a valid answer and stays a successful request."""
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

    response = await connected_client.post(
        "/api/v1/analysis",
        json={"question": "Which customer has id 9999?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_data"
    assert body["answer"] == "No matching rows were returned."
    assert body["error"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failed_analysis_is_still_persisted(connected_client: AsyncClient, fake_llm):
    """The failed turn is stored so it can be replayed as history."""
    fake_llm.install([AIMessage(content="I cannot answer that.")])

    failed = await connected_client.post(
        "/api/v1/analysis",
        json={"question": "How many customers are there?"},
    )
    conversation_id = failed.json()["conversation_id"]

    detail = await connected_client.get(f"/api/v1/conversations/{conversation_id}")

    assert detail.status_code == 200
    assistant = [
        message
        for message in detail.json()["messages"]
        if message["role"] == "assistant"
    ][0]
    assert assistant["status"] == "failed"
    assert assistant["error"] == "No database tool completed successfully."
    assert assistant["content"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_conversation_history_endpoint_for_unknown_conversation(
    connected_client: AsyncClient,
):
    response = await connected_client.get(
        "/api/v1/conversations/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_endpoint(api_client: AsyncClient):
    response = await api_client.get("/api/v1/")

    assert response.status_code == 200
    assert "message" in response.json()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_missing_internal_session_factory_is_reported(api_client: AsyncClient):
    session_factory = app.state.db_client
    app.state.db_client = None
    try:
        response = await api_client.get("/api/v1/conversations")
    finally:
        app.state.db_client = session_factory

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Internal database session factory is not initialized."
    )


# --------------------------------------------------------------------------
# Conversations
# --------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.asyncio
async def test_deleting_an_unknown_conversation_returns_404(api_client: AsyncClient):
    response = await api_client.delete(
        "/api/v1/conversations/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found."


@pytest.mark.integration
@pytest.mark.asyncio
async def test_conversation_listing_can_be_filtered_by_connection(
    connected_client: AsyncClient, fake_llm
):
    fake_llm.install(
        [
            tool_call(
                "execute_sql_query",
                {"query": "SELECT COUNT(*) AS c FROM customers"},
                "call_1",
            ),
            AIMessage(content="There are 4 customers."),
        ]
    )

    created = await connected_client.post(
        "/api/v1/analysis",
        json={"question": "How many customers are there?"},
    )
    conversation_id = created.json()["conversation_id"]

    connection_id = (await connected_client.get("/api/v1/connections")).json()[
        "connection_id"
    ]

    matching = await connected_client.get(
        f"/api/v1/conversations?connection_id={connection_id}"
    )
    assert matching.status_code == 200
    assert [item["id"] for item in matching.json()] == [conversation_id]

    unrelated = await connected_client.get(
        "/api/v1/conversations?connection_id=00000000-0000-0000-0000-000000000000"
    )
    assert unrelated.status_code == 200
    assert unrelated.json() == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_follow_up_after_a_failed_analysis_keeps_the_error_context(
    connected_client: AsyncClient, fake_llm
):
    """A failed turn is stored and replayed to the agent as history."""
    fake_llm.install(
        [AIMessage(content="I cannot answer that.")],
        [
            tool_call(
                "execute_sql_query",
                {"query": "SELECT COUNT(*) AS c FROM customers"},
                "call_1",
            ),
            AIMessage(content="There are 4 customers."),
        ],
    )

    failed = await connected_client.post(
        "/api/v1/analysis",
        json={"question": "How many customers are there?"},
    )
    assert failed.status_code == 500
    assert failed.json()["status"] == "failed"

    conversation_id = failed.json()["conversation_id"]
    assert conversation_id is not None

    follow_up = await connected_client.post(
        "/api/v1/analysis",
        json={
            "question": "Try again please.",
            "conversation_id": conversation_id,
        },
    )
    assert follow_up.status_code == 200
    assert follow_up.json()["status"] == "success"

    prompt = fake_llm.models[1].calls[0]
    assert any(
        "Analysis failed:" in str(message.content) for message in prompt
    ), "the failed turn was not replayed to the agent"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_history_is_not_replayed_when_the_limit_is_zero(
    connected_client: AsyncClient, fake_llm, monkeypatch
):
    from core.config import get_settings

    monkeypatch.setattr(get_settings(), "CHAT_HISTORY_LIMIT", 0)

    fake_llm.install(
        [
            tool_call(
                "execute_sql_query",
                {"query": "SELECT COUNT(*) AS c FROM customers"},
                "call_1",
            ),
            AIMessage(content="There are 4 customers."),
        ],
        [
            tool_call(
                "execute_sql_query",
                {"query": "SELECT COUNT(*) AS c FROM customers"},
                "call_2",
            ),
            AIMessage(content="Still 4 customers."),
        ],
    )

    first = await connected_client.post(
        "/api/v1/analysis",
        json={"question": "How many customers are there?"},
    )
    conversation_id = first.json()["conversation_id"]

    second = await connected_client.post(
        "/api/v1/analysis",
        json={"question": "And now?", "conversation_id": conversation_id},
    )
    assert second.status_code == 200

    prompt = fake_llm.models[1].calls[0]
    assert not any(
        "How many customers are there?" in str(message.content) for message in prompt
    ), "history was replayed although the limit is zero"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reconnecting_reuses_the_connection_record(
    api_client: AsyncClient, sample_db_path: str
):
    first = await api_client.post(
        "/api/v1/connections",
        json={"database_url": f"sqlite:///{sample_db_path}"},
    )
    first_id = first.json()["connection_id"]

    assert (await api_client.delete("/api/v1/connections")).status_code == 204

    second = await api_client.post(
        "/api/v1/connections",
        json={"database_url": f"sqlite:///{sample_db_path}"},
    )
    second_id = second.json()["connection_id"]

    assert second_id == first_id

    async with app.state.db_engine.connect() as connection:
        count = (
            await connection.execute(text("SELECT count(*) FROM connection_record"))
        ).scalar_one()

    assert count == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repository_errors_are_reported_as_500(
    api_client: AsyncClient, monkeypatch
):
    from sqlalchemy.exc import SQLAlchemyError

    async def _boom(self, *args, **kwargs):
        raise SQLAlchemyError("simulated repository failure")

    monkeypatch.setattr(
        "routes.conversations.ConversationRepository.list_all", _boom
    )

    response = await api_client.get("/api/v1/conversations")

    assert response.status_code == 500
    assert response.json()["detail"] == "Could not retrieve conversations."


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repository_errors_are_reported_for_a_single_conversation(
    api_client: AsyncClient, monkeypatch
):
    from sqlalchemy.exc import SQLAlchemyError

    async def _boom(self, *args, **kwargs):
        raise SQLAlchemyError("simulated repository failure")

    monkeypatch.setattr(
        "routes.conversations.ConversationRepository.get", _boom
    )

    response = await api_client.get(
        "/api/v1/conversations/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Could not retrieve conversation."


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repository_errors_are_reported_when_deleting(
    api_client: AsyncClient, monkeypatch
):
    from sqlalchemy.exc import SQLAlchemyError

    async def _boom(self, *args, **kwargs):
        raise SQLAlchemyError("simulated repository failure")

    monkeypatch.setattr(
        "routes.conversations.ConversationRepository.delete", _boom
    )

    response = await api_client.delete(
        "/api/v1/conversations/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Could not delete conversation."


# --------------------------------------------------------------------------
# Schema endpoint error handling
# --------------------------------------------------------------------------
@pytest.fixture
def broken_database(tmp_path):
    """A file that is not a valid SQLite database."""
    path = tmp_path / "broken.db"
    path.write_bytes(b"this is not a sqlite database" * 32)
    return path.as_posix()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_schema_tables_reports_a_broken_database(
    api_client: AsyncClient, broken_database: str
):
    from database.connection import DatabaseConnectionManager

    manager = DatabaseConnectionManager(f"sqlite:///{broken_database}")
    app.state.db_manager = manager

    response = await api_client.get("/api/v1/schema/tables")

    assert response.status_code == 500
    assert response.json()["detail"] == "Could not retrieve database tables."


@pytest.mark.integration
@pytest.mark.asyncio
async def test_schema_table_detail_reports_a_broken_database(
    api_client: AsyncClient, broken_database: str
):
    from database.connection import DatabaseConnectionManager

    manager = DatabaseConnectionManager(f"sqlite:///{broken_database}")
    app.state.db_manager = manager

    response = await api_client.get("/api/v1/schema/tables/customers")

    assert response.status_code == 500
    assert response.json()["detail"] == "Could not inspect database table."


# --------------------------------------------------------------------------
# Connection and analysis error handling
# --------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.asyncio
async def test_registration_failures_are_reported_as_500(
    api_client: AsyncClient, sample_db_path: str, monkeypatch
):
    from sqlalchemy.exc import SQLAlchemyError

    closed: list[object] = []
    original_close = DatabaseConnectionManager.close

    def _spy(self, *args, **kwargs):
        closed.append(self)
        original_close(self)

    monkeypatch.setattr(DatabaseConnectionManager, "close", _spy)

    async def _boom(self, *args, **kwargs):
        raise SQLAlchemyError("simulated registration failure")

    monkeypatch.setattr(
        "routes.connections.ConnectionRepository.register", _boom
    )

    response = await api_client.post(
        "/api/v1/connections",
        json={"database_url": f"sqlite:///{sample_db_path}"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Could not register database connection."
    assert len(closed) == 1, "the manager was not closed after the failure"
    assert app.state.db_manager is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failures_while_closing_the_connection_are_reported(
    connected_client: AsyncClient, monkeypatch
):
    manager = app.state.db_manager

    def _boom() -> None:
        raise RuntimeError("simulated close failure")

    monkeypatch.setattr(manager, "close", _boom)

    try:
        response = await connected_client.delete("/api/v1/connections")

        assert response.status_code == 500
        assert response.json()["detail"] == "Could not close database connection."
    finally:
        monkeypatch.undo()
        app.state.db_manager = None
        app.state.connection_id = None
        manager.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_analysis_requires_a_registered_connection(
    api_client: AsyncClient, sample_db_path: str
):
    """A manager without a registered connection id is refused."""
    manager = DatabaseConnectionManager(f"sqlite:///{sample_db_path}")
    app.state.db_manager = manager
    app.state.connection_id = None

    response = await api_client.post(
        "/api/v1/analysis",
        json={"question": "How many customers are there?"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Active database connection is not registered."
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failures_while_persisting_the_conversation_are_reported(
    connected_client: AsyncClient, fake_llm, monkeypatch
):
    from sqlalchemy.exc import SQLAlchemyError

    fake_llm.install(
        [
            tool_call(
                "execute_sql_query",
                {"query": "SELECT COUNT(*) AS c FROM customers"},
                "call_1",
            ),
            AIMessage(content="There are 4 customers."),
        ]
    )

    async def _boom(self, *args, **kwargs):
        raise SQLAlchemyError("simulated persistence failure")

    monkeypatch.setattr(
        "routes.analysis.ConversationRepository.save_turn", _boom
    )

    response = await connected_client.post(
        "/api/v1/analysis",
        json={"question": "How many customers are there?"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Could not save conversation."


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unexpected_agent_failures_are_reported(
    connected_client: AsyncClient, monkeypatch
):
    """A broken model provider must not leak an internal error."""

    def _boom(self, *args, **kwargs):
        raise RuntimeError("provider is down")

    monkeypatch.setattr(LLMFactory, "create", _boom)

    response = await connected_client.post(
        "/api/v1/analysis",
        json={"question": "How many customers are there?"},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"] == "Analysis failed."
    assert body["answer"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_an_empty_database_url_is_rejected(api_client: AsyncClient):
    response = await api_client.post(
        "/api/v1/connections",
        json={"database_url": "   "},
    )

    assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_the_api_documentation_page_is_served(api_client: AsyncClient):
    response = await api_client.get("/scalar")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_shutdown_closes_the_active_connection(sample_db_path: str):
    """The lifespan must release the external connection on shutdown."""
    manager = DatabaseConnectionManager(f"sqlite:///{sample_db_path}")

    async with app.router.lifespan_context(app):
        app.state.db_manager = manager
        app.state.connection_id = None

    assert manager._engine is None  # noqa: SLF001 - the closed state is the contract
