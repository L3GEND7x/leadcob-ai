"""Private institutional directory. No automatic sending or legacy data copying."""
import re
from sqlalchemy import select, exists
from sqlalchemy.orm import Session
from app.core.account_access import authorize
from app.db.models import WorkspaceContact, WorkspaceSuppression
from app.services.cnpj import clean_cnpj, is_valid_cnpj
from app.services.safe_http import validate_url
from app.collectors.site_contacts import _role_box
from app.api.routes_contacts import clean


def _cnpj(value):
    if not is_valid_cnpj(value):
        raise ValueError('Invalid CNPJ')
    return clean_cnpj(value)


def add_contact(db: Session, token: str, organization_id: int, csrf: str, *,
                cnpj: str, kind: str, value: str, source_url: str, institutional: bool):
    principal = authorize(db, token, organization_id, 'write', csrf=csrf)
    cnpj = _cnpj(cnpj)
    if not institutional or not source_url or len(source_url) > 1000:
        raise ValueError('Institutional source required')
    validate_url(source_url)
    if db.get(WorkspaceSuppression, (principal.organization_id, cnpj)):
        raise ValueError('Suppressed company')
    if len(value) > 500:
        raise ValueError('Contact too long')
    value = clean(kind, value)
    if kind == 'email' and not _role_box(value.split('@')[0]):
        raise ValueError('Institutional mailbox required')
    if kind in {'website', 'linkedin', 'instagram', 'facebook'}:
        validate_url(value)
    if db.scalar(select(WorkspaceContact.id).where(
            WorkspaceContact.organization_id == principal.organization_id,
            WorkspaceContact.cnpj == cnpj, WorkspaceContact.kind == kind,
            WorkspaceContact.value == value)) is not None:
        raise ValueError('Duplicate contact')
    contact = WorkspaceContact(organization_id=principal.organization_id, cnpj=cnpj,
                               kind=kind, value=value, source_url=source_url)
    db.add(contact)
    db.flush()
    return contact


def list_contacts(db: Session, token: str, organization_id: int, *,
                  cnpj: str | None = None, limit: int = 100, offset: int = 0):
    principal = authorize(db, token, organization_id, 'read')
    if not 1 <= limit <= 250 or offset < 0:
        raise ValueError('Invalid pagination')
    suppressed = exists().where(WorkspaceSuppression.organization_id == WorkspaceContact.organization_id,
                                WorkspaceSuppression.cnpj == WorkspaceContact.cnpj)
    query = select(WorkspaceContact).where(
        WorkspaceContact.organization_id == principal.organization_id, ~suppressed)
    if cnpj is not None:
        query = query.where(WorkspaceContact.cnpj == _cnpj(cnpj))
    return list(db.scalars(query.order_by(WorkspaceContact.id.desc()).offset(offset).limit(limit)))


def suppress_company(db: Session, token: str, organization_id: int, csrf: str, *,
                     cnpj: str, reason: str):
    principal = authorize(db, token, organization_id, 'write', csrf=csrf)
    cnpj = _cnpj(cnpj)
    if not reason.strip() or len(reason) > 250:
        raise ValueError('Invalid suppression reason')
    item = db.get(WorkspaceSuppression, (principal.organization_id, cnpj))
    if item is None:
        item = WorkspaceSuppression(organization_id=principal.organization_id, cnpj=cnpj, reason=reason.strip())
        db.add(item)
    db.flush()
    return item
