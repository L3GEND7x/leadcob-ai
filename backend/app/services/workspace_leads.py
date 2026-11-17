"""Tenant-scoped private lead operations. No legacy CRM access."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.account_access import authorize
from app.db.models import WorkspaceLead

STAGES = frozenset({'identified', 'contacted', 'negotiation', 'won', 'lost'})


class LeadNotFound(Exception):
    pass


def list_leads(db: Session, token: str, organization_id: int, *, limit: int = 100, offset: int = 0):
    principal = authorize(db, token, organization_id, 'read')
    if not 1 <= limit <= 250 or offset < 0:
        raise ValueError('Invalid pagination')
    return list(db.scalars(select(WorkspaceLead)
        .where(WorkspaceLead.organization_id == principal.organization_id)
        .order_by(WorkspaceLead.id.desc()).offset(offset).limit(limit)))


def _find(db, organization_id, lead_id):
    item = db.scalar(select(WorkspaceLead).where(
        WorkspaceLead.organization_id == organization_id, WorkspaceLead.id == lead_id))
    if item is None:
        raise LeadNotFound()
    return item


def get_lead(db: Session, token: str, organization_id: int, lead_id: int):
    principal = authorize(db, token, organization_id, 'read')
    return _find(db, principal.organization_id, lead_id)


def _validate(name, notes, stage):
    if not name.strip() or len(name) > 220 or len(notes) > 8000 or stage not in STAGES:
        raise ValueError('Invalid lead fields')


def create_lead(db: Session, token: str, organization_id: int, csrf: str,
                *, name: str, notes: str = '', stage: str = 'identified'):
    principal = authorize(db, token, organization_id, 'write', csrf=csrf)
    _validate(name, notes, stage)
    item = WorkspaceLead(organization_id=principal.organization_id, name=name.strip(), notes=notes, stage=stage)
    db.add(item)
    db.flush()
    return item


def update_lead(db: Session, token: str, organization_id: int, csrf: str,
                lead_id: int, *, name: str, notes: str, stage: str):
    principal = authorize(db, token, organization_id, 'write', csrf=csrf)
    item = _find(db, principal.organization_id, lead_id)
    _validate(name, notes, stage)
    item.name, item.notes, item.stage = name.strip(), notes, stage
    db.flush()
    return item


def delete_lead(db: Session, token: str, organization_id: int, csrf: str, lead_id: int):
    principal = authorize(db, token, organization_id, 'write', csrf=csrf)
    db.delete(_find(db, principal.organization_id, lead_id))
    db.flush()
