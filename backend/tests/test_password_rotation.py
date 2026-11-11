"""Troca de senha do proprietário: sessões abertas com a senha anterior deixam de valer."""
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.security import password_hash, password_matches

ROOT = Path(__file__).resolve().parents[2]


def test_rotating_password_hash_ends_existing_sessions(monkeypatch):
    monkeypatch.setattr(settings, 'admin_username', 'admin')
    monkeypatch.setattr(settings, 'admin_password_hash', password_hash('senha-antiga-de-teste-1234'))
    with TestClient(app) as c:
        assert c.post('/api/auth/login', json={'username': 'admin', 'password': 'senha-antiga-de-teste-1234'}).status_code == 200
        assert c.get('/api/companies/search').status_code == 200
        # A proprietária grava um novo ADMIN_PASSWORD_HASH na Railway e o serviço reinicia.
        monkeypatch.setattr(settings, 'admin_password_hash', password_hash('senha-nova-de-teste-5678'))
        assert c.get('/api/companies/search').status_code == 401
        assert c.get('/api/auth/session').json()['authenticated'] is False
        assert c.post('/api/auth/login', json={'username': 'admin', 'password': 'senha-antiga-de-teste-1234'}).status_code == 401
        assert c.post('/api/auth/login', json={'username': 'admin', 'password': 'senha-nova-de-teste-5678'}).status_code == 200
        assert c.get('/api/companies/search').status_code == 200


def _run_generator(*answers):
    return subprocess.run([sys.executable, '-I', str(ROOT / 'scripts' / 'gerar_hash_senha.py')],
                          input='\n'.join(answers) + '\n', capture_output=True, text=True)


def test_hash_generator_matches_backend_and_never_echoes_password(monkeypatch):
    result = _run_generator('Senha-Nova-Longa-2026!', 'Senha-Nova-Longa-2026!')
    assert result.returncode == 0, result.stderr
    generated = result.stdout.strip().splitlines()[-1]
    assert generated.startswith('pbkdf2_sha256.') and 'Senha-Nova' not in result.stdout + result.stderr
    monkeypatch.setattr(settings, 'admin_password_hash', generated)
    assert password_matches('Senha-Nova-Longa-2026!') and not password_matches('outra-senha-qualquer')


def test_hash_generator_refuses_short_or_mismatched_password():
    short = _run_generator('curta', 'curta')
    assert short.returncode == 1 and 'pbkdf2' not in short.stdout
    mismatch = _run_generator('Senha-Nova-Longa-2026!', 'Senha-Diferente-2026!!')
    assert mismatch.returncode == 1 and 'pbkdf2' not in mismatch.stdout
