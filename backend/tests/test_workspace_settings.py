import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.account_access import AccessDenied, issue_session
from app.core.security import password_hash
from app.db.database import Base
from app.db.models import AccountUser, Membership, Organization, WorkspaceSettings
from app.services.workspace_settings import get_settings, update_settings


def test_private_settings():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        a = Organization(name='Teste A', slug='a', active=True)
        b = Organization(name='Teste B', slug='b', active=True)
        u = AccountUser(email='a@example.org', password_hash=password_hash('test-password-long-a'), active=True)
        v = AccountUser(email='b@example.org', password_hash=password_hash('test-password-long-b'), active=True)
        db.add_all([a, b, u, v])
        db.flush()
        db.add_all([Membership(user_id=u.id, organization_id=a.id, role='admin', active=True),
                    Membership(user_id=v.id, organization_id=b.id, role='member', active=True)])
        db.commit()
        ta, ca = issue_session(db, u.email, 'test-password-long-a', a.id)
        tb, cb = issue_session(db, v.email, 'test-password-long-b', b.id)
        defaults = get_settings(db, tb, b.id)
        assert defaults['followup_days'] == [3, 7, 14]
        fields = dict(timezone_name='UTC', followup_days=[2, 5, 10], default_page_size=100)
        result = update_settings(db, ta, a.id, ca, **fields)
        db.commit()
        assert result['timezone'] == 'UTC'
        assert result['followup_days'] == [2, 5, 10]
        assert db.get(WorkspaceSettings, a.id).updated_by == u.id
        assert get_settings(db, tb, b.id) == defaults
        assert db.get(WorkspaceSettings, b.id) is None
        with pytest.raises(AccessDenied):
            get_settings(db, ta, b.id)
        with pytest.raises(AccessDenied):
            update_settings(db, ta, b.id, ca, **fields)
        with pytest.raises(AccessDenied):
            update_settings(db, tb, b.id, cb, **fields)
        with pytest.raises(AccessDenied):
            update_settings(db, ta, a.id, 'wrong', **fields)
        for changes in ({'timezone_name': 'No/SuchZone'}, {'default_page_size': 251},
                        {'followup_days': [5, 2]}, {'followup_days': [1, 1]},
                        {'followup_days': [True]}, {'followup_days': []}):
            with pytest.raises(ValueError):
                update_settings(db, ta, a.id, ca, **(fields | changes))
        assert get_settings(db, ta, a.id) == result
    engine.dispose()
