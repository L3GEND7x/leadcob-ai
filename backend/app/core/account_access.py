"""Internal commercial identity services. Not connected to legacy HTTP routes."""
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.core.security import password_hash, stamp
from app.db.models import AccountUser, AccountSession, Organization, Membership


@dataclass(frozen=True)
class Principal:
    user_id: int
    organization_id: int
    role: str


class AccessDenied(Exception):
    """Uniform denial without disclosing account or organization existence."""


PERMISSIONS = {
    'admin': frozenset({'read', 'write', 'manage_members'}),
    'member': frozenset({'read', 'write'}),
    'viewer': frozenset({'read'}),
}


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _membership(db: Session, user_id: int, organization_id: int):
    row = db.execute(
        select(Membership.role, AccountUser.active, Organization.active, Membership.active)
        .join(AccountUser, AccountUser.id == Membership.user_id)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(Membership.user_id == user_id, Membership.organization_id == organization_id)
    ).one_or_none()
    if not row or not all(row[1:]) or row[0] not in PERMISSIONS:
        raise AccessDenied()
    return Principal(user_id, organization_id, row[0])


def issue_session(db: Session, email: str, password: str, organization_id: int):
    """Caller owns transaction. Must be protected by rate limiting before HTTP exposure."""
    user = db.scalar(select(AccountUser).where(AccountUser.email == email.strip().casefold()))
    # Perform comparable work for absent accounts and malformed hashes.
    stored = user.password_hash if user else ''
    parts = stored.split('.')
    valid_format = (len(parts) == 3 and parts[0] == 'pbkdf2_sha256'
                    and len(parts[1]) == 32 and len(parts[2]) == 64
                    and all(c in '0123456789abcdef' for c in parts[1] + parts[2]))
    salt = parts[1] if valid_format else '0' * 32
    computed = password_hash(password, salt)
    if not valid_format or not hmac.compare_digest(computed, stored) or user is None:
        raise AccessDenied()
    principal = _membership(db, user.id, organization_id)
    raw, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
    db.add(AccountSession(token_hash=_digest(raw), user_id=principal.user_id,
                          organization_id=principal.organization_id, csrf_token=csrf,
                          expires_at=datetime.now(timezone.utc) + timedelta(hours=8)))
    db.flush()
    return raw, csrf


def authorize(db: Session, raw: str, organization_id: int, permission: str,
              *, csrf: str | None = None) -> Principal:
    """Recheck membership on every operation, reject cross-organization sessions.
    Write and management permission always require CSRF, including for administrators.
    """
    if not raw or len(raw) > 128:
        raise AccessDenied()
    row = db.execute(select(AccountSession.user_id, AccountSession.organization_id,
                            AccountSession.expires_at, AccountSession.csrf_token)
                     .where(AccountSession.token_hash == _digest(raw))).one_or_none()
    if not row or row.organization_id != organization_id:
        raise AccessDenied()
    if stamp(row.expires_at) <= datetime.now(timezone.utc):
        raise AccessDenied()
    principal = _membership(db, row.user_id, organization_id)
    if permission not in PERMISSIONS[principal.role]:
        raise AccessDenied()
    if permission != 'read' and (not csrf or not hmac.compare_digest(csrf.encode('utf-8'), row.csrf_token.encode('utf-8'))):
        raise AccessDenied()
    return principal


def revoke_session(db: Session, raw: str):
    db.execute(delete(AccountSession).where(AccountSession.token_hash == _digest(raw)))


def revoke_user_sessions(db: Session, user_id: int):
    """Call transactionally when changing a user's password or disabling their account."""
    db.execute(delete(AccountSession).where(AccountSession.user_id == user_id))
