import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.account_access import AccessDenied, issue_session
from app.core.security import password_hash
from app.db.database import Base
from app.db.models import AccountUser, Membership, Organization
from app.services.workspace_contacts import add_contact, list_contacts, suppress_company


def test_private_directory():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        a = Organization(name='Teste A', slug='a', active=True)
        b = Organization(name='Teste B', slug='b', active=True)
        u = AccountUser(email='a@example.org', password_hash=password_hash('test-password-long-a'), active=True)
        v = AccountUser(email='b@example.org', password_hash=password_hash('test-password-long-b'), active=True)
        db.add_all([a, b, u, v])
        db.flush()
        db.add_all([Membership(user_id=u.id, organization_id=a.id, role='member', active=True),
                    Membership(user_id=v.id, organization_id=b.id, role='admin', active=True)])
        db.commit()
        ta, ca = issue_session(db, u.email, 'test-password-long-a', a.id)
        tb, cb = issue_session(db, v.email, 'test-password-long-b', b.id)
        fields = dict(cnpj='12.345.678/0001-95', kind='email', value='financeiro@example.org',
                      source_url='https://example.org/contato', institutional=True)
        x = add_contact(db, ta, a.id, ca, **fields)
        y = add_contact(db, tb, b.id, cb, **fields)
        db.commit()
        assert [r.id for r in list_contacts(db, ta, a.id)] == [x.id]
        assert [r.id for r in list_contacts(db, tb, b.id)] == [y.id]
        with pytest.raises(AccessDenied):
            list_contacts(db, ta, b.id)
        with pytest.raises(ValueError):
            add_contact(db, ta, a.id, ca, **fields)
        for changes in ({'value': 'nome.sobrenome@example.org'}, {'institutional': False},
                        {'source_url': 'http://127.0.0.1'}, {'cnpj': '123'}):
            with pytest.raises(ValueError):
                add_contact(db, ta, a.id, ca, **(fields | changes))
        suppress_company(db, ta, a.id, ca, cnpj=fields['cnpj'], reason='Opt-out')
        assert list_contacts(db, ta, a.id) == []
        assert [r.id for r in list_contacts(db, tb, b.id)] == [y.id]
        with pytest.raises(ValueError):
            add_contact(db, ta, a.id, ca, **(fields | {'value': 'contato@example.org'}))
        db.get(Membership, (v.id, b.id)).role = 'viewer'
        db.commit()
        with pytest.raises(AccessDenied):
            suppress_company(db, tb, b.id, cb, cnpj=fields['cnpj'], reason='Blocked')
    engine.dispose()
