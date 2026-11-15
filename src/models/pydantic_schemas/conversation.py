from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ConversationSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    connection_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime
    message_count: int


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str | None
    status: str | None
    queries: list[dict[str, Any]] | None
    schema_results: list[dict[str, Any]] | None
    metadata: dict[str, Any] | None
    error: str | None
    created_at: datetime


class ConversationDetailResponse(ConversationSummaryResponse):
    messages: list[MessageResponse]
