import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from database.repositories import ConversationRepository
from models.db_schemas import Conversation
from models.pydantic_schemas import (
    ConversationDetailResponse,
    ConversationSummaryResponse,
    MessageResponse,
)
from routes.dependencies import get_internal_db

logger = logging.getLogger(__name__)

conversations_router = APIRouter(
    prefix="/api/v1/conversations",
    tags=["Conversations"],
)


def _summary(conversation: Conversation, message_count: int | None = None):
    return ConversationSummaryResponse(
        id=conversation.id,
        connection_id=conversation.connection_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=(
            len(conversation.messages) if message_count is None else message_count
        ),
    )


@conversations_router.get("", response_model=list[ConversationSummaryResponse])
async def get_conversations(connection_id: UUID | None = None,
                        db: AsyncSession = Depends(get_internal_db)):  # noqa: B008

    try:
        conversations = await ConversationRepository(db).list_all(connection_id)
        return [
            _summary(conversation, message_count)
            for conversation, message_count in conversations
        ]
    except SQLAlchemyError:
        logger.exception("Failed to retrieve conversations.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve conversations.",
        ) from None


@conversations_router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation_detail(conversation_id: UUID,
                            db: AsyncSession = Depends(get_internal_db)):  # noqa: B008

    try:
        conversation = await ConversationRepository(db).get(conversation_id)
    except SQLAlchemyError:
        logger.exception(f"Failed to retrieve conversation {conversation_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve conversation.",
        ) from None

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    return ConversationDetailResponse(
        **_summary(conversation).model_dump(),
        messages=[
            MessageResponse(
                id=message.id,
                conversation_id=message.conversation_id,
                role=message.role,
                content=message.content,
                status=message.status,
                queries=message.queries,
                schema_results=message.schema_results,
                metadata=message.metadata_json,
                error=message.error,
                created_at=message.created_at,
            )
            for message in conversation.messages
        ],
    )


@conversations_router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_conversation(conversation_id: UUID,
                        db: AsyncSession = Depends(get_internal_db)):  # noqa: B008
    
    try:
        deleted = await ConversationRepository(db).delete(conversation_id)
        if not deleted:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found.",
            )
        await db.commit()
    except HTTPException:
        raise
    except SQLAlchemyError:
        await db.rollback()
        logger.exception(f"Failed to delete conversation {conversation_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete conversation.",
        ) from None

    return Response(status_code=status.HTTP_204_NO_CONTENT)