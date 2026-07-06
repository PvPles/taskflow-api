import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import TaskStatus, User
from app.schemas.tasks import TaskCreate, TaskOut, TaskPageOut, TaskUpdate
from app.services import tasks as service
from app.services.projects import get_project_for_member

router = APIRouter(tags=["tasks"])


@router.post("/projects/{project_id}/tasks", status_code=201, response_model=TaskOut)
def create_task(
    project_id: uuid.UUID,
    body: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Any project member. New tasks start in 'todo'."""
    project = get_project_for_member(db, project_id, user)
    return service.create_task(db, project, user, body)


@router.get("/projects/{project_id}/tasks", response_model=TaskPageOut)
def list_tasks(
    project_id: uuid.UUID,
    status: TaskStatus | None = None,
    assignee_id: uuid.UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Cursor-paginated, newest first. Pass the returned next_cursor to get
    the following page; null next_cursor means you reached the end."""
    project = get_project_for_member(db, project_id, user)
    items, next_cursor = service.list_tasks(db, project, status, assignee_id, limit, cursor)
    return TaskPageOut(items=items, next_cursor=next_cursor)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _, task = service.get_task_for_member(db, task_id, user)
    return task


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Status changes are validated: todo <-> in_progress <-> done, and a done
    task must be reopened (todo) before going back in progress."""
    project, task = service.get_task_for_member(db, task_id, user)
    return service.update_task(db, project, task, body)


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Task creator or project owner."""
    project, task = service.get_task_for_member(db, task_id, user)
    service.delete_task(db, project, task, user)
    return Response(status_code=204)
