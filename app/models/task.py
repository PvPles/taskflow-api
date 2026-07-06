import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaskStatus(enum.StrEnum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


# A done task must be reopened (moved back to todo) before it can be
# in_progress again; that's the whole point of the transition table.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    TaskStatus.todo.value: {TaskStatus.in_progress.value, TaskStatus.done.value},
    TaskStatus.in_progress.value: {TaskStatus.todo.value, TaskStatus.done.value},
    TaskStatus.done.value: {TaskStatus.todo.value},
}


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        # Backs the cursor-paginated task list: (project, created_at desc, id desc)
        Index("ix_tasks_project_created", "project_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=TaskStatus.todo.value, server_default=TaskStatus.todo.value
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Python-side default (not just server_default): the pagination cursor
    # compares created_at for equality, which needs microsecond precision and
    # an identical storage format on SQLite - CURRENT_TIMESTAMP has neither.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
