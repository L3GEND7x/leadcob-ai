from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.core.security import password_hash
from app.core.account_access import issue_session
from app.db.database import SessionLocal
from app.db.models import (AccountUser, AccountSession, Membership, Organization,
    WorkspaceLead, WorkspaceTask, WorkspacePortfolio, WorkspacePortfolioTitle,
    WorkspaceContact, WorkspaceSuppression, WorkspaceSettings)


def test_workspace_http_boundary(monkeypatch):
    monkeypatch.setattr(settings, 'admin_password_hash', password_hash('owner-test-password-long'))
    monkeypatch.setattr(settings, 'public_url', '')
    monkeypatch.setattr(settings, 'commercial_auth_enabled', True)
    suffix = uuid4().hex
    with TestClient(app) as a, TestClient(app) as b:
        with SessionLocal() as db:
            org_a = Organization(name='Test A', slug=suffix+'a', active=True)
            org_b = Organization(name='Test B', slug=suffix+'b', active=True)
            user_a = AccountUser(email=suffix+'a@example.org', password_hash=password_hash('test-password-long-a'), active=True)
            user_b = AccountUser(email=suffix+'b@example.org', password_hash=password_hash('test-password-long-b'), active=True)
            db.add_all([org_a, org_b, user_a, user_b])
            db.flush()
            oa, ob, ua, ub = org_a.id, org_b.id, user_a.id, user_b.id
            db.add_all([Membership(user_id=ua, organization_id=oa, role='member', active=True),
                        Membership(user_id=ub, organization_id=ob, role='admin', active=True)])
            db.flush()
            ta, ca = issue_session(db, user_a.email, 'test-password-long-a', oa)
            tb, cb = issue_session(db, user_b.email, 'test-password-long-b', ob)
            db.commit()
        a.cookies.set('leadcob_commercial_session', ta)
        b.cookies.set('leadcob_commercial_session', tb)
        pa = f'/api/commercial/workspace/{oa}'
        pb = f'/api/commercial/workspace/{ob}'
        ha = {'Origin':'http://testserver', 'X-CSRF-Token':ca}
        hb = {'Origin':'http://testserver', 'X-CSRF-Token':cb}
        try:
            with TestClient(app) as anonymous:
                assert anonymous.get(pa+'/leads').status_code == 403
            assert a.get('/api/companies/search').status_code == 401
            assert a.get(pb+'/leads').status_code == 403
            assert a.post(pa+'/leads', json={'name':'bad'}).status_code == 403
            assert a.post(pa+'/leads', json={'name':'bad','organization_id':ob}, headers=ha).status_code == 422
            x = a.post(pa+'/leads', json={'name':'Private A'}, headers=ha)
            y = b.post(pb+'/leads', json={'name':'Private B'}, headers=hb)
            assert x.status_code == 201 and y.status_code == 201
            xid, yid = x.json()['id'], y.json()['id']
            assert [r['id'] for r in a.get(pa+'/leads').json()] == [xid]
            assert a.get(pa+f'/leads/{yid}').status_code == 404
            assert a.put(pa+f'/leads/{yid}', json={'name':'bad'}, headers=ha).status_code == 404
            assert a.delete(pa+f'/leads/{yid}', headers=ha).status_code == 404
            assert a.put(pa+f'/leads/{xid}', json={'name':'Updated','stage':'contacted'}, headers=ha).status_code == 200
            task = b.post(pb+'/tasks', json={'title':'Private task','due_date':'2026-11-20'}, headers=hb)
            assert task.status_code == 201
            tid = task.json()['id']
            assert a.get(pa+'/tasks').json() == []
            assert a.patch(pa+f'/tasks/{tid}',json={'completed':True},headers=ha).status_code == 404
            assert b.patch(pb+f'/tasks/{tid}',json={'completed':True},headers=hb).status_code == 200
            portfolio = b.post(pb+'/portfolios',json={'name':'Private portfolio','reference_date':'2026-11-01'},headers=hb)
            assert portfolio.status_code == 201
            pid = portfolio.json()['id']
            path = f'/portfolios/{pid}/titles'
            assert a.get(pa+path).status_code == 404
            assert a.post(pa+path,json={'reference':'bad','amount':'1.00','due_date':'2026-11-01'},headers=ha).status_code == 404
            for ref, amount in [('T1','0.10'),('T2','0.20')]:
                response = b.post(pb+path,json={'reference':ref,'amount':amount,'due_date':'2026-11-01'},headers=hb)
                assert response.status_code == 201, response.text
            assert b.get(pb+f'/portfolios/{pid}/summary',params={'as_of':'2026-11-17'}).json()['total'] == '0.30'
            contact = dict(cnpj='12.345.678/0001-95', kind='email', value='financeiro@example.org',
                           source_url='https://example.org/contato', institutional=True)
            assert b.post(pb+'/contacts', json=contact, headers=hb).status_code == 201
            assert a.get(pa+'/contacts').json() == []
            assert a.get(pb+'/contacts').status_code == 403
            assert b.post(pb+'/contacts', json=contact, headers=hb).status_code == 422
            assert b.get(pb+'/contacts').json()[0]['status'] == 'a_verificar'
            assert b.post(pb+'/suppressions', json={'cnpj':contact['cnpj'],'reason':'Opt-out'}, headers=hb).status_code == 201
            assert b.get(pb+'/contacts').json() == []
            prefs = dict(timezone_name='UTC', followup_days=[2,5], default_page_size=100)
            assert a.put(pa+'/settings', json=prefs, headers=ha).status_code == 403
            assert b.put(pb+'/settings', json=prefs, headers=hb).status_code == 200
            assert a.get(pa+'/settings').json()['timezone'] == 'America/Manaus'
            assert b.get(pb+'/settings').json()['timezone'] == 'UTC'
            with SessionLocal() as db:
                db.get(Membership,(ub,ob)).role = 'viewer'
                db.commit()
            assert b.get(pb+path).status_code == 200
            assert b.delete(pb+f'/leads/{yid}',headers=hb).status_code == 403
            monkeypatch.setattr(settings,'commercial_auth_enabled',False)
            assert b.get(pb+'/leads').status_code == 404
        finally:
            with SessionLocal() as db:
                ids = [oa, ob]
                portfolio_ids = [p.id for p in db.query(WorkspacePortfolio).filter(WorkspacePortfolio.organization_id.in_(ids))]
                db.query(WorkspacePortfolioTitle).filter(WorkspacePortfolioTitle.portfolio_id.in_(portfolio_ids)).delete(synchronize_session=False)
                for model in (WorkspaceSettings, WorkspaceSuppression, WorkspaceContact, WorkspacePortfolio, WorkspaceTask, WorkspaceLead, AccountSession, Membership):
                    db.query(model).filter(model.organization_id.in_(ids)).delete(synchronize_session=False)
                db.query(AccountUser).filter(AccountUser.id.in_([ua,ub])).delete(synchronize_session=False)
                db.query(Organization).filter(Organization.id.in_(ids)).delete(synchronize_session=False)
                db.commit()
