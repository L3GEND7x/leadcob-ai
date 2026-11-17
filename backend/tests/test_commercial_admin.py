from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.core.security import password_hash
from app.db.database import SessionLocal
from app.db.models import AccountUser, AccountSession, Membership, Organization, AuditLog


def test_owner_provisions_private_workspace(monkeypatch):
    monkeypatch.setattr(settings, 'admin_password_hash', password_hash('owner-long-password-test'))
    monkeypatch.setattr(settings, 'admin_username', 'owner-'+uuid4().hex)
    monkeypatch.setattr(settings, 'public_url', '')
    monkeypatch.setattr(settings, 'commercial_auth_enabled', True)
    slug = 'test-'+uuid4().hex
    email = slug+'@example.org'
    payload = dict(name='Test organization', slug=slug, email=email, password='long-commercial-test-password')
    base = '/api/owner/commercial/organizations'
    origin = {'Origin':'http://testserver'}
    with TestClient(app) as owner, TestClient(app) as member:
        assert member.get(base).status_code == 401
        login = owner.post('/api/auth/login',json={'username':settings.admin_username,'password':'owner-long-password-test'})
        assert login.status_code == 200
        headers = {**origin,'X-CSRF-Token':login.json()['csrf_token']}
        try:
            assert owner.post(base,json=payload,headers=origin).status_code == 403
            p = owner.post(base,json=payload,headers=headers)
            assert p.status_code == 201, p.text
            oid = p.json()['id']
            assert owner.post(base,json=payload,headers=headers).status_code == 409
            assert 'password' not in p.text
            assert owner.get(base+f'/{oid}/members').json()[0]['role'] == 'admin'
            result = member.post('/api/commercial/auth/login',json=dict(email=email,password=payload['password'],organization_id=oid),headers=origin)
            assert result.status_code == 200
            assert member.get(base).status_code == 401
            assert owner.patch(base+f'/{oid}',json={'active':False},headers=headers).status_code == 200
            assert member.get('/api/commercial/auth/session',params={'organization_id':oid}).json()['authenticated'] is False
        finally:
            with SessionLocal() as db:
                org = db.query(Organization).filter_by(slug=slug).first()
                user = db.query(AccountUser).filter_by(email=email).first()
                if org:
                    db.query(AccountSession).filter_by(organization_id=org.id).delete()
                    db.query(Membership).filter_by(organization_id=org.id).delete()
                    db.query(AuditLog).filter_by(entity_type='organization',entity_id=org.id).delete()
                    db.delete(org)
                if user:
                    db.delete(user)
                db.commit()
