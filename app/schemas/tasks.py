import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskStatus


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    due_at: datetime | None = None
    assignee_id: uuid.UUID | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    due_at: datetime | None = None
    assignee_id: uuid.UUID | None = None
    status: TaskStatus | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    status: TaskStatus
    assignee_id: uuid.UUID | None
    due_at: datetime | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class TaskPageOut(BaseModel):
    items: list[TaskOut]
    next_cursor: str | None
