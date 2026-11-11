import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.security import password_hash, validate_configuration
from app.db.database import normalized_database_url


ROOT = Path(__file__).resolve().parents[2]


def test_managed_postgres_url_and_production_validation(monkeypatch):
    monkeypatch.setattr(settings, 'db_host', '')
    monkeypatch.setattr(settings, 'postgres_password', '')
    monkeypatch.setattr(settings, 'database_url', 'postgresql://owner:p%40ss@postgres.internal:5432/leadcob')
    parsed = make_url(normalized_database_url())
    assert parsed.drivername == 'postgresql+psycopg'
    assert parsed.password == 'p@ss'
    monkeypatch.setattr(settings, 'app_env', 'production')
    monkeypatch.setattr(settings, 'admin_password_hash', password_hash('senha-de-teste-muito-forte'))
    monkeypatch.setattr(settings, 'public_url', 'https://leadcob.up.railway.app')
    monkeypatch.setattr(settings, 'demo_seed', False)
    validate_configuration()
    monkeypatch.setattr(settings, 'database_url', 'sqlite:///./leadcob.db')
    with pytest.raises(RuntimeError, match='PostgreSQL'):
        validate_configuration()


def test_railway_backup_verifies_dump_before_upload(tmp_path):
    fake = tmp_path / 'bin'
    fake.mkdir()
    log = tmp_path / 'calls'
    for name, script in {
        'pg_dump': '#!/bin/sh\nfor arg in "$@"; do case "$arg" in --file=*) printf dump > "${arg#--file=}";; esac; done\n',
        'pg_restore': '#!/bin/sh\n[ "${FAIL_RESTORE:-}" != 1 ]\n',
        'restic': '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n'
                  'if [ "$1" = cat ]; then exit 0; fi\nexit 0\n',
    }.items():
        path = fake / name
        path.write_text(script)
        path.chmod(0o755)
    env = {**os.environ, 'PATH': f'{fake}:{os.environ["PATH"]}', 'CALLS': str(log),
           'PGHOST': 'postgres.internal', 'PGUSER': 'owner', 'PGPASSWORD': 'test',
           'PGDATABASE': 'leadcob', 'RESTIC_REPOSITORY': 's3:https://s3.example.com/bucket',
           'RESTIC_PASSWORD': 'test-password', 'AWS_ACCESS_KEY_ID': 'test-id',
           'AWS_SECRET_ACCESS_KEY': 'test-secret'}
    script = ROOT / 'infra' / 'railway-backup.sh'
    failed = subprocess.run(['sh', str(script)], env={**env, 'FAIL_RESTORE': '1'}, capture_output=True)
    assert failed.returncode != 0 and not log.exists()
    succeeded = subprocess.run(['sh', str(script)], env=env, capture_output=True)
    assert succeeded.returncode == 0, succeeded.stderr
    assert 'backup ' in log.read_text() and 'check' in log.read_text()
    dump_path = next(line.split()[1] for line in log.read_text().splitlines() if line.startswith('backup '))
    assert not Path(dump_path).exists()
