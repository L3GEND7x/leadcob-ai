import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.account_access import AccessDenied, issue_session
from app.core.security import password_hash
from app.db.database import Base
from app.db.models import AccountUser, Company, Membership, Organization
from app.services.workspace_leads import (
    LeadNotFound, create_lead, delete_lead, get_lead, list_leads, update_lead,
)


def test_private_leads_isolation():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        a = Organization(name='Teste A', slug='a', active=True)
        b = Organization(name='Teste B', slug='b', active=True)
        u = AccountUser(email='a@example.org', password_hash=password_hash('senha-teste-a-longa'), active=True)
        v = AccountUser(email='b@example.org', password_hash=password_hash('senha-teste-b-longa'), active=True)
        db.add_all([a, b, u, v, Company(name='Registro legado privado')])
        db.flush()
        db.add_all([Membership(user_id=u.id, organization_id=a.id, role='member', active=True),
                    Membership(user_id=v.id, organization_id=b.id, role='admin', active=True)])
        db.commit()
        ta, ca = issue_session(db, u.email, 'senha-teste-a-longa', a.id)
        tb, cb = issue_session(db, v.email, 'senha-teste-b-longa', b.id)
        x = create_lead(db, ta, a.id, ca, name='Lead A', notes='privado A')
        y = create_lead(db, tb, b.id, cb, name='Lead B', notes='privado B')
        db.commit()
        assert [r.id for r in list_leads(db, ta, a.id)] == [x.id]
        assert [r.id for r in list_leads(db, tb, b.id)] == [y.id]
        with pytest.raises(AccessDenied):
            list_leads(db, ta, b.id)
        with pytest.raises(LeadNotFound):
            get_lead(db, ta, a.id, y.id)
        with pytest.raises(LeadNotFound):
            update_lead(db, ta, a.id, ca, y.id, name='intruso', notes='', stage='won')
        with pytest.raises(LeadNotFound):
            delete_lead(db, ta, a.id, ca, y.id)
        with pytest.raises(AccessDenied):
            create_lead(db, ta, a.id, 'wrong', name='invalid')
        update_lead(db, ta, a.id, ca, x.id, name='Lead atualizado', notes='ok', stage='contacted')
        assert get_lead(db, tb, b.id, y.id).notes == 'privado B'
        db.get(Membership, (v.id, b.id)).role = 'viewer'
        db.commit()
        assert get_lead(db, tb, b.id, y.id).name == 'Lead B'
        with pytest.raises(AccessDenied):
            delete_lead(db, tb, b.id, cb, y.id)
        delete_lead(db, ta, a.id, ca, x.id)
        assert list_leads(db, ta, a.id) == []
        assert len(list_leads(db, tb, b.id)) == 1
    engine.dispose()
