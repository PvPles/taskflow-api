import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.projects import (
    MemberAddIn,
    MemberOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)
from app.services import projects as service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", status_code=201, response_model=ProjectOut)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a project. The caller becomes its owner."""
    return service.create_project(db, user, body.name, body.description)


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """All projects the caller owns or is a member of, newest first."""
    return service.list_projects(db, user)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return service.get_project_for_member(db, project_id, user)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Owner only."""
    project = service.get_project_for_member(db, project_id, user)
    service.require_owner(project, user)
    return service.update_project(db, project, body.name, body.description)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Owner only. Cascades to tasks and comments."""
    project = service.get_project_for_member(db, project_id, user)
    service.require_owner(project, user)
    service.delete_project(db, project)
    return Response(status_code=204)


@router.get("/{project_id}/members", response_model=list[MemberOut])
def list_members(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = service.get_project_for_member(db, project_id, user)
    return service.list_members(db, project)


@router.post("/{project_id}/members", status_code=201, response_model=list[MemberOut])
def add_member(
    project_id: uuid.UUID,
    body: MemberAddIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Owner only. Adds an existing account by email."""
    project = service.get_project_for_member(db, project_id, user)
    service.require_owner(project, user)
    service.add_member(db, project, body.email)
    return service.list_members(db, project)


@router.delete("/{project_id}/members/{member_user_id}", status_code=204)
def remove_member(
    project_id: uuid.UUID,
    member_user_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Owner only."""
    project = service.get_project_for_member(db, project_id, user)
    service.require_owner(project, user)
    service.remove_member(db, project, member_user_id)
    return Response(status_code=204)
