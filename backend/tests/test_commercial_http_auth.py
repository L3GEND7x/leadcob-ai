from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.core.security import password_hash
from app.db.database import SessionLocal
from app.db.models import AccountUser, Membership, Organization, AccountSession


def test_commercial_http_isolated(monkeypatch):
    monkeypatch.setattr(settings, 'admin_password_hash', password_hash('owner-test-password-long'))
    monkeypatch.setattr(settings, 'public_url', '')
    monkeypatch.setattr(settings, 'commercial_auth_enabled', False)
    suffix = uuid4().hex
    email = suffix + '@example.org'
    base = '/api/commercial/auth'
    origin = {'Origin': 'http://testserver'}
    with TestClient(app) as c:
        with SessionLocal() as db:
            org = Organization(name='Test', slug=suffix, active=True)
            user = AccountUser(email=email, password_hash=password_hash('commercial-test-password-long'), active=True)
            other = Organization(name='Other', slug=suffix+'b', active=True)
            db.add_all([org, user, other])
            db.flush()
            oid, uid, other_id = org.id, user.id, other.id
            db.add(Membership(user_id=uid, organization_id=oid, role='viewer', active=True))
            db.commit()
        payload = dict(email=email, password='commercial-test-password-long', organization_id=oid)
        try:
            assert c.post(base+'/login', json=payload, headers=origin).status_code == 404
            monkeypatch.setattr(settings, 'commercial_auth_enabled', True)
            assert c.post(base+'/login', json=payload).status_code == 403
            result = c.post(base+'/login', json=payload, headers=origin)
            assert result.status_code == 200, result.text
            csrf = result.json()['csrf_token']
            assert 'HttpOnly' in result.headers['set-cookie']
            assert c.get(base+'/session', params={'organization_id':oid}).json()['role'] == 'viewer'
            assert not c.get(base+'/session', params={'organization_id':other_id}).json()['authenticated']
            assert c.get('/api/companies/search').status_code == 401
            assert c.post(base+'/logout', json={'organization_id':oid}, headers=origin).status_code == 403
            assert c.post(base+'/logout', json={'organization_id':oid}, headers={**origin,'X-CSRF-Token':csrf}).status_code == 200
            assert not c.get(base+'/session', params={'organization_id':oid}).json()['authenticated']
            payload['password'] = 'incorrect'
            for _ in range(4):
                assert c.post(base+'/login', json=payload, headers=origin).status_code == 401
            assert c.post(base+'/login', json=payload, headers=origin).status_code == 429
        finally:
            with SessionLocal() as db:
                db.query(AccountSession).filter_by(user_id=uid).delete()
                db.query(Membership).filter_by(user_id=uid).delete()
                db.query(AccountUser).filter_by(id=uid).delete()
                db.query(Organization).filter(Organization.id.in_([oid, other_id])).delete(synchronize_session=False)
                db.commit()
