"""Persistence: SQLAlchemy 2.0 models (SQLite by default, PostgreSQL via DATABASE_URL)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class FormSession(Base):
    """One user filling one uploaded form."""

    __tablename__ = "form_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    filename: Mapped[str] = mapped_column(String(255))
    template_path: Mapped[str] = mapped_column(String(1024))
    form_id: Mapped[str | None] = mapped_column(String(64))  # known form id, None = generic
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    schema: Mapped[list] = mapped_column(JSON)  # snapshot of the field schema
    state: Mapped[dict] = mapped_column(JSON, default=dict)  # ConversationState
    phase: Mapped[str] = mapped_column(String(20), default="collecting")
    pdf_path: Mapped[str | None] = mapped_column(String(1024))

    messages: Mapped[list["Message"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="Message.id")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("form_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(32))  # llm | rule | rule-fallback
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[FormSession] = relationship(back_populates="messages")


def make_sessionmaker(database_url: str):
    kwargs = {"connect_args": {"check_same_thread": False}} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, future=True, **kwargs)
    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _pragmas(conn, _):  # WAL: readers don't block the writer; enforce FKs
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
