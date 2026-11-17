from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.core.security import password_hash


def test_commercial_page(monkeypatch):
    monkeypatch.setattr(settings, 'admin_password_hash', password_hash('owner-test-password-long'))
    monkeypatch.setattr(settings, 'commercial_auth_enabled', False)
    with TestClient(app) as c:
        assert c.get('/commercial').status_code == 404
        monkeypatch.setattr(settings, 'commercial_auth_enabled', True)
        r = c.get('/commercial')
        assert r.status_code == 200
        assert 'no-store' in r.headers['cache-control']
        assert 'login-form' in r.text
        assert c.get('/static/commercial.js').status_code == 200
        assert c.get('/static/commercial.css').status_code == 200
        assert c.get('/api/companies/search').status_code == 401
