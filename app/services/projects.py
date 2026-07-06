import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.models import Project, ProjectMember, User
from app.schemas.projects import MemberOut


def create_project(db: Session, owner: User, name: str, description: str | None) -> Project:
    project = Project(name=name, description=description, owner_id=owner.id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def list_projects(db: Session, user: User) -> list[Project]:
    member_project_ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
    return list(
        db.scalars(
            select(Project)
            .where(or_(Project.owner_id == user.id, Project.id.in_(member_project_ids)))
            .order_by(Project.created_at.desc())
        )
    )


def is_member(db: Session, project: Project, user_id: uuid.UUID) -> bool:
    if project.owner_id == user_id:
        return True
    return db.get(ProjectMember, {"project_id": project.id, "user_id": user_id}) is not None


def get_project_for_member(db: Session, project_id: uuid.UUID, user: User) -> Project:
    """Non-members get the same 404 as a nonexistent project - membership is
    not leaked to outsiders."""
    project = db.get(Project, project_id)
    if project is None or not is_member(db, project, user.id):
        raise APIError(404, "project_not_found", "Project not found")
    return project


def require_owner(project: Project, user: User) -> None:
    if project.owner_id != user.id:
        raise APIError(403, "forbidden", "Only the project owner can do this")


def update_project(
    db: Session, project: Project, name: str | None, description: str | None
) -> Project:
    if name is not None:
        project.name = name
    if description is not None:
        project.description = description
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project: Project) -> None:
    db.delete(project)
    db.commit()


def add_member(db: Session, project: Project, email: str) -> ProjectMember:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise APIError(404, "user_not_found", "No account with this email")
    if is_member(db, project, user.id):
        raise APIError(409, "already_member", "This user is already a project member")
    member = ProjectMember(project_id=project.id, user_id=user.id)
    db.add(member)
    db.commit()
    return member


def remove_member(db: Session, project: Project, user_id: uuid.UUID) -> None:
    if user_id == project.owner_id:
        raise APIError(409, "cannot_remove_owner", "The project owner cannot be removed")
    member = db.get(ProjectMember, {"project_id": project.id, "user_id": user_id})
    if member is None:
        raise APIError(404, "member_not_found", "This user is not a project member")
    db.delete(member)
    db.commit()


def list_members(db: Session, project: Project) -> list[MemberOut]:
    owner = db.get(User, project.owner_id)
    members = [
        MemberOut(
            user_id=owner.id,
            email=owner.email,
            display_name=owner.display_name,
            is_owner=True,
            added_at=project.created_at,
        )
    ]
    rows = db.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project.id)
        .order_by(ProjectMember.added_at)
    )
    for membership, user in rows:
        members.append(
            MemberOut(
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
                is_owner=False,
                added_at=membership.added_at,
            )
        )
    return members
