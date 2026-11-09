import uuid

from sqlalchemy import VARCHAR, Column, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .retailops_base import SQLAlchemyBase


class ConnectionRecord(SQLAlchemyBase):
    
    __tablename__ = "connection_record"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    
    fingerprint = Column(VARCHAR(255), unique=True, nullable=False, index=True)
        
    dialect = Column(VARCHAR(50), nullable=False)
    safe_url = Column(VARCHAR(500), nullable=False)
    database_name = Column(VARCHAR(100), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_connected_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)
    
    conversations = relationship(
        "Conversation",
        back_populates="connection",
        cascade="all, delete-orphan",
        passive_deletes=True
    )