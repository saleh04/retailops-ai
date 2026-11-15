import uuid

from sqlalchemy import VARCHAR, Column, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from .retailops_base import SQLAlchemyBase


class Message(SQLAlchemyBase):
    __tablename__ = "message"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    role = Column(VARCHAR(50), nullable=False)
    content = Column(Text, nullable=True)
    status = Column(VARCHAR(50), nullable=True)
    
    queries = Column(JSONB, nullable=True)
    schema_results = Column(JSONB, nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation = relationship("Conversation", back_populates="messages")