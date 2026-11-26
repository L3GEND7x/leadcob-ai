"""IP real atrás do proxy para limitar tentativas de login (TRUSTED_PROXY_CIDRS, desligado por padrão)."""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.client_ip import client_ip
from app.core.config import settings
from app.core.security import password_hash
from app.db.database import ensure_schema
from app.main import app

ensure_schema()


def req(peer, real=None):
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers={"x-real-ip": real} if real else {})


def test_header_ignored_by_default(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "")
    assert client_ip(req("100.64.0.7", "203.0.113.9")) == "100.64.0.7"


def test_header_used_only_from_trusted_proxy(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "100.64.0.0/10")
    assert client_ip(req("100.64.0.7", "203.0.113.9")) == "203.0.113.9"
    assert client_ip(req("198.51.100.4", "203.0.113.9")) == "198.51.100.4"   # conexão direta: não confia
    assert client_ip(req("100.64.0.7", "não-é-ip")) == "100.64.0.7"
    assert client_ip(req("100.64.0.7")) == "100.64.0.7"


def test_invalid_cidr_never_widens_trust(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "lixo, 999.1.1.1/8")
    assert client_ip(req("100.64.0.7", "203.0.113.9")) == "100.64.0.7"


def _attempts(monkeypatch, username, proxies, real_ip):
    monkeypatch.setattr(settings, "admin_username", "dona")
    monkeypatch.setattr(settings, "admin_password_hash", password_hash("senha-correta-muito-longa"))
    codes = []
    for proxy in proxies:
        with TestClient(app, client=(proxy, 50000)) as c:
            codes.append(c.post("/api/auth/login", json={"username": username, "password": "errada"},
                                headers={"X-Real-IP": real_ip}).status_code)
    return codes


def test_proxy_rotation_spreads_attempts_without_setting(monkeypatch):
    """Reproduz a produção: cada tentativa chega por um endereço diferente do proxy e nunca é bloqueada."""
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "")
    codes = _attempts(monkeypatch, "rotacao-sem-config", [f"100.64.0.{i}" for i in range(2, 10)], "203.0.113.50")
    assert 429 not in codes


def test_real_ip_groups_attempts_behind_rotating_proxy(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_cidrs", "100.64.0.0/10")
    codes = _attempts(monkeypatch, "rotacao-com-config", [f"100.64.0.{i}" for i in range(2, 10)], "203.0.113.51")
    assert codes[:5] == [401] * 5 and codes[5] == 429   # a 6ª tentativa do mesmo visitante é bloqueada
    other = _attempts(monkeypatch, "rotacao-com-config", ["100.64.0.30"], "203.0.113.99")
    assert other == [401]   # outro visitante não fica bloqueado pelo primeiro
