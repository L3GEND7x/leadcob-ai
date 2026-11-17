from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.account_access import AccessDenied, authorize, issue_session, revoke_session, revoke_user_sessions
from app.core.security import password_hash
from app.db.database import Base
from app.db.models import AccountUser, AccountSession, Membership, Organization


@pytest.fixture
def accounts():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        a = Organization(name='Teste A', slug='a', active=True)
        b = Organization(name='Teste B', slug='b', active=True)
        u = AccountUser(email='user@example.org', password_hash=password_hash('test-password-long'), active=True)
        db.add_all([a, b, u])
        db.flush()
        db.add_all([Membership(user_id=u.id, organization_id=a.id, role='viewer', active=True),
                    Membership(user_id=u.id, organization_id=b.id, role='admin', active=True)])
        db.commit()
        yield db, u.id, a.id, b.id
    engine.dispose()


def test_scope_role_and_csrf(accounts):
    db, uid, a, b = accounts
    raw, csrf = issue_session(db, 'USER@example.org', 'test-password-long', a)
    db.commit()
    assert authorize(db, raw, a, 'read').user_id == uid
    with pytest.raises(AccessDenied):
        authorize(db, raw, b, 'read')
    with pytest.raises(AccessDenied):
        authorize(db, raw, a, 'write', csrf=csrf)
    admin, admin_csrf = issue_session(db, 'user@example.org', 'test-password-long', b)
    assert authorize(db, admin, b, 'manage_members', csrf=admin_csrf).role == 'admin'
    with pytest.raises(AccessDenied):
        authorize(db, admin, b, 'write', csrf='wrong')
    with pytest.raises(AccessDenied):
        authorize(db, admin, b, 'unknown', csrf=admin_csrf)
    assert db.scalar(select(AccountSession).where(AccountSession.token_hash == raw)) is None


def test_revocation_and_expiry(accounts):
    db, uid, a, b = accounts
    raw, _ = issue_session(db, 'user@example.org', 'test-password-long', a)
    db.commit()
    membership = db.get(Membership, (uid, a))
    membership.active = False
    db.commit()
    with pytest.raises(AccessDenied):
        authorize(db, raw, a, 'read')
    with pytest.raises(AccessDenied):
        issue_session(db, 'user@example.org', 'test-password-long', a)
    raw2, _ = issue_session(db, 'user@example.org', 'test-password-long', b)
    revoke_session(db, raw2)
    with pytest.raises(AccessDenied):
        authorize(db, raw2, b, 'read')
    raw3, _ = issue_session(db, 'user@example.org', 'test-password-long', b)
    row = db.scalar(select(AccountSession).where(AccountSession.organization_id == b))
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    with pytest.raises(AccessDenied):
        authorize(db, raw3, b, 'read')
    raw4, _ = issue_session(db, 'user@example.org', 'test-password-long', b)
    revoke_user_sessions(db, uid)
    with pytest.raises(AccessDenied):
        authorize(db, raw4, b, 'read')


def test_invalid_credentials_and_disabled_org(accounts):
    db, uid, a, b = accounts
    for email, password in [('missing@example.org', 'test-password-long'), ('user@example.org', 'wrong')]:
        with pytest.raises(AccessDenied):
            issue_session(db, email, password, a)
    db.get(Organization, b).active = False
    db.commit()
    with pytest.raises(AccessDenied):
        issue_session(db, 'user@example.org', 'test-password-long', b)
