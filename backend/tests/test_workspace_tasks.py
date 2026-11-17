import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.account_access import AccessDenied, issue_session
from app.core.security import password_hash
from app.db.database import Base
from app.db.models import AccountUser, Membership, Organization
from app.services.workspace_tasks import TaskNotFound, create_task, delete_task, list_tasks, set_completed


def test_private_agenda():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        a = Organization(name='A', slug='a', active=True)
        b = Organization(name='B', slug='b', active=True)
        u = AccountUser(email='a@example.org', password_hash=password_hash('test-long-password-a'), active=True)
        v = AccountUser(email='b@example.org', password_hash=password_hash('test-long-password-b'), active=True)
        db.add_all([a, b, u, v])
        db.flush()
        db.add_all([Membership(user_id=u.id, organization_id=a.id, role='member', active=True),
                    Membership(user_id=v.id, organization_id=b.id, role='admin', active=True)])
        db.commit()
        ta, ca = issue_session(db, u.email, 'test-long-password-a', a.id)
        tb, cb = issue_session(db, v.email, 'test-long-password-b', b.id)
        x = create_task(db, ta, a.id, ca, title='A privado', due_date='2026-11-20')
        y = create_task(db, tb, b.id, cb, title='B privado', due_date='2026-11-21')
        db.commit()
        assert [t.id for t in list_tasks(db, ta, a.id)] == [x.id]
        with pytest.raises(AccessDenied):
            list_tasks(db, ta, b.id)
        with pytest.raises(TaskNotFound):
            set_completed(db, ta, a.id, ca, y.id, completed=True)
        with pytest.raises(TaskNotFound):
            delete_task(db, ta, a.id, ca, y.id)
        with pytest.raises(AccessDenied):
            set_completed(db, ta, a.id, 'wrong', x.id, completed=True)
        with pytest.raises(ValueError):
            create_task(db, ta, a.id, ca, title='Invalid', due_date='2026-02-30')
        set_completed(db, ta, a.id, ca, x.id, completed=True)
        assert [t.id for t in list_tasks(db, ta, a.id, completed=True)] == [x.id]
        assert list_tasks(db, ta, a.id, completed=False) == []
        set_completed(db, ta, a.id, ca, x.id, completed=False)
        assert [t.id for t in list_tasks(db, ta, a.id, completed=False)] == [x.id]
        db.get(Membership, (v.id, b.id)).role = 'viewer'
        db.commit()
        with pytest.raises(AccessDenied):
            delete_task(db, tb, b.id, cb, y.id)
        assert [t.id for t in list_tasks(db, tb, b.id)] == [y.id]
        delete_task(db, ta, a.id, ca, x.id)
        assert list_tasks(db, ta, a.id) == []
    engine.dispose()
