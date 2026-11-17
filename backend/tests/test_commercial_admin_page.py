from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.core.security import password_hash


def test_owner_admin_page(monkeypatch):
    monkeypatch.setattr(settings, 'admin_password_hash', password_hash('owner-long-password-test'))
    monkeypatch.setattr(settings, 'admin_username', 'owner-'+uuid4().hex)
    monkeypatch.setattr(settings, 'public_url', '')
    with TestClient(app) as c:
        assert c.get('/owner/commercial').status_code == 401
        c.cookies.set('leadcob_commercial_session', 'not-an-owner-cookie')
        assert c.get('/owner/commercial').status_code == 401
        login = c.post('/api/auth/login', json={'username':settings.admin_username,'password':'owner-long-password-test'})
        assert login.status_code == 200
        page = c.get('/owner/commercial')
        assert page.status_code == 200
        assert 'no-store' in page.headers['cache-control']
        assert 'provision' in page.text
        assert c.get('/static/commercial-admin.js').status_code == 200
