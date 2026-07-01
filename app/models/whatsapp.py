from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database.db import Base


class WhatsAppUserPreference(Base):
    __tablename__ = "whatsapp_user_preferences"

    user_id = Column(String(32), primary_key=True, index=True)
    source_language = Column(String(64), nullable=False, default="English")
    target_language = Column(String(16), nullable=False, default="eng")
    mode = Column(String(16), nullable=False, default="chat")
    tts_enabled = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
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
    timestamp = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


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
    timestamp = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WhatsAppInboundEvent(Base):
    """Tracks inbound WhatsApp webhook messages for cross-instance dedup.

    A unique ``message_id`` provides an atomic claim: the first instance to
    insert a row wins; other instances (or Meta retries) see the existing row
    and skip. Only used for inbound webhook dedup — never mixed with the
    inbound/outbound rows in ``whatsapp_messages``.
    """

    __tablename__ = "whatsapp_inbound_events"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(255), nullable=False, unique=True, index=True)
    user_id = Column(String(32), nullable=True, index=True)
    # status: 'processing' | 'processed' | 'failed'
    status = Column(String(16), nullable=False, default="processing")
    attempts = Column(Integer, nullable=False, default=1)
    last_error = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


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
