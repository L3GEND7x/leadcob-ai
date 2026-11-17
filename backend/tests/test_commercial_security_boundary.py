from datetime import datetime, timezone, timedelta
import hashlib
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import Organization, AccountUser, Membership, AccountSession, WorkspaceLead
from app.core.account_access import authorize, AccessDenied
from app.services.workspace_leads import get_lead, LeadNotFound


def test_tenant_role_csrf_and_revocation():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        a = Organization(name="A", slug="audit-a", active=True)
        b = Organization(name="B", slug="audit-b", active=True)
        user = AccountUser(email="audit@example.test", password_hash="unused", active=True)
        db.add_all([a,b,user])
        db.flush()
        db.add(Membership(user_id=user.id, organization_id=a.id, role="viewer", active=True))
        db.add(AccountSession(token_hash=hashlib.sha256(b"audit-token").hexdigest(),
                              user_id=user.id, organization_id=a.id, csrf_token="csrf",
                              expires_at=datetime.now(timezone.utc)+timedelta(hours=1)))
        other = WorkspaceLead(organization_id=b.id, name="Private")
        db.add(other)
        db.commit()
        assert authorize(db,"audit-token",a.id,"read").role == "viewer"
        with pytest.raises(AccessDenied):
            authorize(db,"audit-token",b.id,"read")
        with pytest.raises(LeadNotFound):
            get_lead(db,"audit-token",a.id,other.id)
        with pytest.raises(AccessDenied):
            authorize(db,"audit-token",a.id,"write",csrf="csrf")
        member = db.get(Membership,(user.id,a.id))
        member.role = "member"
        db.commit()
        with pytest.raises(AccessDenied):
            authorize(db,"audit-token",a.id,"write",csrf="é")
        assert authorize(db,"audit-token",a.id,"write",csrf="csrf").role == "member"
        a.active = False
        db.commit()
        with pytest.raises(AccessDenied):
            authorize(db,"audit-token",a.id,"read")
    engine.dispose()
