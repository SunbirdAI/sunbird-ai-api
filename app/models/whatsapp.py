from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database.db import Base


class WhatsAppUserPreference(Base):
    __tablename__ = "whatsapp_user_preferences"

    user_id = Column(String(32), primary_key=True, index=True)
    source_language = Column(String(64), nullable=False, default="English")
    target_language = Column(String(16), nullable=False, default="eng")
    mode = Column(String(16), nullable=False, default="chat")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class WhatsAppMessage(Base):
    __tablename__ = "whatsapp_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(32), nullable=False, index=True)
    message_text = Column(Text, nullable=False, default="")
    message_type = Column(String(32), nullable=False, index=True)
    user_message = Column(Text, nullable=True)
    message_id = Column(String(255), nullable=True, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WhatsAppFeedback(Base):
    __tablename__ = "whatsapp_feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(32), nullable=True, index=True)
    sender_name = Column(String(255), nullable=True)
    message_id = Column(String(255), nullable=True, index=True)
    user_message = Column(Text, nullable=False, default="")
    bot_response = Column(Text, nullable=False, default="")
    feedback = Column(String(64), nullable=False)
    feedback_type = Column(String(32), nullable=False, default="reaction")
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WhatsAppUserMemory(Base):
    __tablename__ = "whatsapp_user_memory"

    user_id = Column(String(32), primary_key=True, index=True)
    memory_note = Column(Text, nullable=False, default="")
    last_summarized_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
