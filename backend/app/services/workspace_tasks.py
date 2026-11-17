"""Private agenda service; callers own transactions."""
from datetime import date, datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.account_access import authorize
from app.db.models import WorkspaceTask


class TaskNotFound(Exception):
    pass


def _find(db, org, task_id):
    task = db.scalar(select(WorkspaceTask).where(
        WorkspaceTask.organization_id == org, WorkspaceTask.id == task_id))
    if task is None:
        raise TaskNotFound()
    return task


def create_task(db: Session, token: str, organization_id: int, csrf: str, *, title: str, due_date: str):
    principal = authorize(db, token, organization_id, 'write', csrf=csrf)
    if not title.strip() or len(title) > 250 or date.fromisoformat(due_date).isoformat() != due_date:
        raise ValueError('Invalid task fields')
    task = WorkspaceTask(organization_id=principal.organization_id, title=title.strip(), due_date=due_date)
    db.add(task)
    db.flush()
    return task


def list_tasks(db: Session, token: str, organization_id: int, *, completed: bool | None = None,
               limit: int = 100, offset: int = 0):
    principal = authorize(db, token, organization_id, 'read')
    if not 1 <= limit <= 250 or offset < 0:
        raise ValueError('Invalid pagination')
    query = select(WorkspaceTask).where(WorkspaceTask.organization_id == principal.organization_id)
    if completed is not None:
        query = query.where(WorkspaceTask.completed_at.is_not(None) if completed else WorkspaceTask.completed_at.is_(None))
    return list(db.scalars(query.order_by(WorkspaceTask.due_date, WorkspaceTask.id).offset(offset).limit(limit)))


def set_completed(db: Session, token: str, organization_id: int, csrf: str, task_id: int, *, completed: bool):
    principal = authorize(db, token, organization_id, 'write', csrf=csrf)
    task = _find(db, principal.organization_id, task_id)
    if completed and task.completed_at is None:
        task.completed_at = datetime.now(timezone.utc)
    elif not completed:
        task.completed_at = None
    db.flush()
    return task


def delete_task(db: Session, token: str, organization_id: int, csrf: str, task_id: int):
    principal = authorize(db, token, organization_id, 'write', csrf=csrf)
    db.delete(_find(db, principal.organization_id, task_id))
    db.flush()
