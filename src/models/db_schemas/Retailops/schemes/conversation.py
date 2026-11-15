import uuid

from sqlalchemy import VARCHAR, Column, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .retailops_base import SQLAlchemyBase


class Conversation(SQLAlchemyBase):
    __tablename__ = "conversation"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("connection_record.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    title = Column(VARCHAR(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    
    connection = relationship("ConnectionRecord", back_populates="conversations")
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.created_at"
    )

