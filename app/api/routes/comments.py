import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.comments import CommentCreate, CommentOut
from app.services import comments as service
from app.services.tasks import get_task_for_member

router = APIRouter(tags=["comments"])


@router.post("/tasks/{task_id}/comments", status_code=201, response_model=CommentOut)
def add_comment(
    task_id: uuid.UUID,
    body: CommentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Any project member."""
    _, task = get_task_for_member(db, task_id, user)
    return service.add_comment(db, task, user, body.body)


@router.get("/tasks/{task_id}/comments", response_model=list[CommentOut])
def list_comments(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Oldest first."""
    _, task = get_task_for_member(db, task_id, user)
    return service.list_comments(db, task)


@router.delete("/comments/{comment_id}", status_code=204)
def delete_comment(
    comment_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Comment author or project owner."""
    project, comment = service.get_comment_for_member(db, comment_id, user)
    service.delete_comment(db, project, comment, user)
    return Response(status_code=204)
