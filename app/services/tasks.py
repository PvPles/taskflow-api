import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.core.pagination import decode_cursor, encode_cursor
from app.models import Project, Task, TaskStatus, User
from app.models.task import ALLOWED_TRANSITIONS
from app.schemas.tasks import TaskCreate, TaskUpdate
from app.services.projects import get_project_for_member, is_member


def _require_assignable(db: Session, project: Project, assignee_id: uuid.UUID) -> None:
    if not is_member(db, project, assignee_id):
        raise APIError(409, "assignee_not_member", "Assignee must be a project member")


def _validate_transition(current: str, new: str) -> None:
    if current == new:
        return
    if new not in ALLOWED_TRANSITIONS.get(current, set()):
        hint = " - reopen it (move to 'todo') first" if current == TaskStatus.done.value else ""
        raise APIError(
            409,
            "invalid_status_transition",
            f"Cannot move task from '{current}' to '{new}'{hint}",
        )


def create_task(db: Session, project: Project, user: User, data: TaskCreate) -> Task:
    if data.assignee_id is not None:
        _require_assignable(db, project, data.assignee_id)
    task = Task(
        project_id=project.id,
        title=data.title,
        description=data.description,
        due_at=data.due_at,
        assignee_id=data.assignee_id,
        created_by=user.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task_for_member(db: Session, task_id: uuid.UUID, user: User) -> tuple[Project, Task]:
    task = db.get(Task, task_id)
    if task is None:
        raise APIError(404, "task_not_found", "Task not found")
    # Non-members get the project 404, not a task 404 (no existence leak).
    project = get_project_for_member(db, task.project_id, user)
    return project, task


def update_task(db: Session, project: Project, task: Task, data: TaskUpdate) -> Task:
    fields = data.model_dump(exclude_unset=True)
    if "status" in fields and fields["status"] is not None:
        _validate_transition(task.status, fields["status"].value)
        task.status = fields["status"].value
    if "assignee_id" in fields:
        if fields["assignee_id"] is not None:
            _require_assignable(db, project, fields["assignee_id"])
        task.assignee_id = fields["assignee_id"]
    for name in ("title", "description", "due_at"):
        if name in fields:
            setattr(task, name, fields[name])
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, project: Project, task: Task, user: User) -> None:
    if user.id not in (task.created_by, project.owner_id):
        raise APIError(403, "forbidden", "Only the task creator or project owner can delete a task")
    db.delete(task)
    db.commit()


def list_tasks(
    db: Session,
    project: Project,
    status: TaskStatus | None,
    assignee_id: uuid.UUID | None,
    limit: int,
    cursor: str | None,
) -> tuple[list[Task], str | None]:
    """Newest first, keyset-paginated on (created_at, id). The id tie-breaker
    matters: Postgres gives every row in one transaction the same now()."""
    query = select(Task).where(Task.project_id == project.id)
    if status is not None:
        query = query.where(Task.status == status.value)
    if assignee_id is not None:
        query = query.where(Task.assignee_id == assignee_id)
    if cursor is not None:
        after_time, after_id = decode_cursor(cursor)
        query = query.where(
            or_(
                Task.created_at < after_time,
                and_(Task.created_at == after_time, Task.id < after_id),
            )
        )
    query = query.order_by(Task.created_at.desc(), Task.id.desc()).limit(limit + 1)

    rows = list(db.scalars(query))
    items = rows[:limit]
    next_cursor = None
    if len(rows) > limit and items:
        last = items[-1]
        next_cursor = encode_cursor(last.created_at, last.id)
    return items, next_cursor
