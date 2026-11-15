from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.db_schemas import Conversation, Message
from models.enums.chat_enums import MessageRole
from models.pydantic_schemas.analysis import AnalysisResponse


class ConversationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, connection_id: UUID, first_question: str):
        title = " ".join(first_question.split())[:255]
        conversation = Conversation(connection_id=connection_id, title=title)
        self.db.add(conversation)
        await self.db.flush()
        return conversation

    async def get(self, conversation_id: UUID):
        result = await self.db.execute(
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self, connection_id: UUID | None = None):
        statement = (
            select(
                Conversation,
                func.count(Message.id).label("message_count"),
            )
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .group_by(Conversation.id)
            .order_by(Conversation.updated_at.desc())
        )
        if connection_id is not None:
            statement = statement.where(Conversation.connection_id == connection_id)

        result = await self.db.execute(statement)
        return list(result.all())

    async def delete(self, conversation_id: UUID) -> bool:
        conversation = await self.db.get(Conversation, conversation_id)
        if conversation is None:
            return False

        await self.db.delete(conversation)
        return True

    async def build_agent_history(self, conversation_id: UUID, limit: int):
    
        if limit <= 0:
            return []

        result = await self.db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role.in_(
                    [MessageRole.USER.value, MessageRole.ASSISTANT.value]
                )
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        
        history = []
        for message in reversed(result.scalars().all()):

            content = message.content or ""
            if message.role == MessageRole.ASSISTANT.value:
                executed_sql = [
                    query["executed_sql"]
                    for query in message.queries or []
                    if isinstance(query, dict)
                    and query.get("status") == "success"
                    and query.get("executed_sql")
                ]
                if executed_sql:
                    sql_context = "\n".join(f"[Executed SQL: {sql}]" for sql in executed_sql)
                    content = f"{content}\n{sql_context}".strip()
                elif not content and message.error:
                    content = f"Analysis failed: {message.error}"

            history.append({"role": message.role, "content": content})

        return history

    async def save_turn(self, conversation_id: UUID, question: str,
                        analysis_response: AnalysisResponse):

        conversation = await self.db.get(
            Conversation, conversation_id, with_for_update=True
        )
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} does not exist.")

        response_data = analysis_response.model_dump(mode="json")

        user_created_at = datetime.now(UTC)
        assistant_created_at = user_created_at + timedelta(microseconds=1)

        self.db.add_all(
            [
                Message(
                    conversation_id=conversation_id,
                    role=MessageRole.USER.value,
                    content=question,
                    created_at=user_created_at
                ),
                Message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT.value,
                    content=analysis_response.answer,
                    status=analysis_response.status,
                    queries=response_data["queries"],
                    schema_results=response_data["schema_results"],
                    metadata_json=response_data["metadata"],
                    error=analysis_response.error,
                    created_at=assistant_created_at
                ),
            ]
        )
        conversation.updated_at = func.now()
        await self.db.flush()