import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.models import Comment, Project, Task, User
from app.services.projects import get_project_for_member


def add_comment(db: Session, task: Task, author: User, body: str) -> Comment:
    comment = Comment(task_id=task.id, author_id=author.id, body=body)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def list_comments(db: Session, task: Task) -> list[Comment]:
    return list(
        db.scalars(
            select(Comment)
            .where(Comment.task_id == task.id)
            .order_by(Comment.created_at, Comment.id)
        )
    )


def get_comment_for_member(
    db: Session, comment_id: uuid.UUID, user: User
) -> tuple[Project, Comment]:
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise APIError(404, "comment_not_found", "Comment not found")
    task = db.get(Task, comment.task_id)
    project = get_project_for_member(db, task.project_id, user)
    return project, comment


def delete_comment(db: Session, project: Project, comment: Comment, user: User) -> None:
    if user.id not in (comment.author_id, project.owner_id):
        raise APIError(
            403, "forbidden", "Only the comment author or project owner can delete a comment"
        )
    db.delete(comment)
    db.commit()
