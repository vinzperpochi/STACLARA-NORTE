"""Resident-to-official messaging and automated customer-service models."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import Boolean, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import StatusMixin, TimestampedModel

class MessageThread(StatusMixin, TimestampedModel):
    __tablename__ = "message_threads"
    __table_args__ = (
        UniqueConstraint("resident_id", name="uq_message_threads_resident"),
        Index("ix_message_threads_status_last_message", "status", "last_message_at"),
    )
    resident_id: Mapped[int] = mapped_column(ForeignKey("residents.id", ondelete="CASCADE"), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False, default="General assistance")
    last_message_at: Mapped[datetime] = mapped_column(nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resident: Mapped["Resident"] = relationship()
    messages: Mapped[list["Message"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", order_by="Message.created_at"
    )

class Message(TimestampedModel):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_thread_created", "thread_id", "created_at"),)
    thread_id: Mapped[int] = mapped_column(ForeignKey("message_threads.id", ondelete="CASCADE"), nullable=False)
    sender_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)  # RESIDENT, OFFICIAL, BOT
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    thread: Mapped[MessageThread] = relationship(back_populates="messages")
    sender: Mapped["User | None"] = relationship()
