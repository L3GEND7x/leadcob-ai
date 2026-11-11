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
           'RESTIC_PASSWORD': 'test-password', 'AWS_ACCESS_KEY_ID': 'testkeyid0000001',
           'AWS_SECRET_ACCESS_KEY': 'test-secret'}
    script = ROOT / 'infra' / 'railway-backup.sh'
    failed = subprocess.run(['sh', str(script)], env={**env, 'FAIL_RESTORE': '1'}, capture_output=True)
    assert failed.returncode != 0 and not log.exists()
    succeeded = subprocess.run(['sh', str(script)], env=env, capture_output=True)
    assert succeeded.returncode == 0, succeeded.stderr
    assert 'backup ' in log.read_text() and 'check' in log.read_text()
    dump_path = next(line.split()[1] for line in log.read_text().splitlines() if line.startswith('backup '))
    assert not Path(dump_path).exists()


def _fake_tools(tmp_path):
    fake = tmp_path / 'bin'
    fake.mkdir(exist_ok=True)
    log = tmp_path / 'calls'
    for name, script in {
        'pg_dump': '#!/bin/sh\nprintf "pg_dump\\n" >> "$CALLS"\n'
                   'for arg in "$@"; do case "$arg" in --file=*) printf dump > "${arg#--file=}";; esac; done\n',
        'pg_restore': '#!/bin/sh\nexit 0\n',
        'restic': '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\nexit 0\n',
    }.items():
        path = fake / name
        path.write_text(script)
        path.chmod(0o755)
    env = {'PATH': f'{fake}:/usr/bin:/bin', 'CALLS': str(log), 'HOME': str(tmp_path),
           'PGHOST': 'postgres.internal', 'PGUSER': 'owner', 'PGPASSWORD': 'test', 'PGDATABASE': 'leadcob',
           'RESTIC_REPOSITORY': 's3:https://s3.us-east-005.example.com/bucket-privado',
           'RESTIC_PASSWORD': 'senha-restic-de-teste', 'AWS_ACCESS_KEY_ID': '005fakefakefakefake0000001',
           'AWS_SECRET_ACCESS_KEY': 'K005segredoFalsoDeTeste'}
    return env, log


SECRET_MARK = 'VALORSIGILOSO'


@pytest.mark.parametrize('name,value,expected', [
    ('AWS_ACCESS_KEY_ID', f'005{SECRET_MARK}0001\n', 'quebra de linha'),
    ('AWS_ACCESS_KEY_ID', f'005{SECRET_MARK}0001\r', 'quebra de linha'),
    ('AWS_ACCESS_KEY_ID', f'005{SECRET_MARK}\nK005outra', 'quebra de linha'),
    ('AWS_ACCESS_KEY_ID', f'keyID: 005{SECRET_MARK}', 'só letras e números'),
    ('AWS_ACCESS_KEY_ID', f'"005{SECRET_MARK}"', 'só letras e números'),
    ('AWS_ACCESS_KEY_ID', f'005{SECRET_MARK}\t', 'controle'),
    ('AWS_ACCESS_KEY_ID', 'abc', '3 caracteres'),
    ('AWS_SECRET_ACCESS_KEY', f'K005{SECRET_MARK}\n', 'quebra de linha'),
    ('AWS_SECRET_ACCESS_KEY', f'K005 {SECRET_MARK}', 'espaço'),
    ('AWS_SECRET_ACCESS_KEY', '005fakefakefakefake0000001', 'mesmo valor'),
    ('RESTIC_PASSWORD', f'{SECRET_MARK}\n', 'quebra de linha'),
    ('AWS_DEFAULT_REGION', 'us-east-005\n', 'quebra de linha'),
    ('AWS_SESSION_TOKEN', SECRET_MARK, 'token de sessão'),
    ('RESTIC_REPOSITORY', 's3:https://s3.us-east-005.example.com', 'bucket'),
    ('RESTIC_REPOSITORY', 's3:http://s3.example.com/bucket', 'TLS'),
    ('AWS_ACCESS_KEY_ID', '', 'ausente'),
])
def test_railway_backup_rejects_bad_configuration_without_revealing_it(tmp_path, name, value, expected):
    env, log = _fake_tools(tmp_path)
    env[name] = value
    for shell in ['sh', 'busybox'] if _has_busybox() else ['sh']:
        args = [shell, 'sh'] if shell == 'busybox' else [shell]
        result = subprocess.run([*args, str(ROOT / 'infra' / 'railway-backup.sh')], env=env, capture_output=True, text=True)
        assert result.returncode != 0
        output = result.stdout + result.stderr
        assert name in output and expected in output, output
        assert SECRET_MARK not in output and 'segredoFalso' not in output and 'fakefake' not in output
        assert not log.exists()   # falha antes do dump e antes de qualquer chamada ao Restic


def test_railway_backup_reports_each_stage_and_latest_snapshot(tmp_path):
    env, log = _fake_tools(tmp_path)
    result = subprocess.run(['sh', str(ROOT / 'infra' / 'railway-backup.sh')], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    calls = log.read_text().splitlines()
    assert calls[0] == 'pg_dump' and calls[1] == 'cat config'
    assert calls[2].startswith('backup ') and calls[3] == 'check'
    assert calls[4] == 'snapshots --tag leadcob --latest 1'
    assert 'Configuração conferida (keyID com 26 caracteres' in result.stdout
    assert 'BACKUP CONCLUÍDO' in result.stdout
    assert 'fakefake' not in result.stdout + result.stderr and 'segredoFalso' not in result.stdout + result.stderr


def _has_busybox():
    from shutil import which
    return which('busybox') is not None


def _drill_env(tmp_path, tables='0'):
    env, log = _fake_tools(tmp_path)
    fake = tmp_path / 'bin'
    # psql falso: responde a contagem de tabelas e registra o banco usado em cada chamada.
    (fake / 'psql').write_text('#!/bin/sh\nprintf "psql %s@%s\\n" "$PGDATABASE" "$PGHOST" >> "$CALLS"\n'
                               f'case "$*" in *count*pg_tables*) echo {tables};; *) cat >/dev/null; echo "companies 3";; esac\n')
    (fake / 'pg_restore').write_text('#!/bin/sh\nprintf "pg_restore %s %s@%s\\n" "$*" "$PGDATABASE" "$PGHOST" >> "$CALLS"\n')
    (fake / 'restic').write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n'
                                 'if [ "$1" = restore ]; then while [ $# -gt 0 ]; do [ "$1" = --target ] && t=$2; shift; done; '
                                 'mkdir -p "$t/tmp/x" && printf dump > "$t/tmp/x/leadcob-20261111T000000Z.dump"; fi\n')
    for name in ('psql', 'pg_restore', 'restic'):
        (fake / name).chmod(0o755)
    env.update({'RESTORE_PGHOST': 'postgres-ensaio.internal', 'RESTORE_PGUSER': 'ensaio', 'RESTORE_PGPASSWORD': 'x',
                'RESTORE_PGDATABASE': 'ensaio', 'RESTORE_CONFIRM_ISOLATED': 'sim'})
    return env, log


def _drill(env):
    return subprocess.run(['sh', str(ROOT / 'infra' / 'railway-restore-drill.sh')], env=env, capture_output=True, text=True)


def test_restore_drill_writes_only_to_isolated_database(tmp_path):
    env, log = _drill_env(tmp_path)
    result = _drill(env)
    assert result.returncode == 0, result.stderr
    calls = log.read_text()
    assert 'restore latest --tag leadcob' in calls
    assert '--no-owner --no-acl --exit-on-error --dbname=ensaio' in calls
    assert 'postgres.internal' not in calls          # nenhuma chamada ao banco de produção
    assert 'ENSAIO DE RESTAURAÇÃO CONCLUÍDO' in result.stdout and 'companies 3' in result.stdout


@pytest.mark.parametrize('change,expected', [
    ({'RESTORE_CONFIRM_ISOLATED': ''}, 'RESTORE_CONFIRM_ISOLATED=sim'),
    ({'RESTORE_PGHOST': 'postgres.internal', 'RESTORE_PGDATABASE': 'leadcob'}, 'mesmo servidor e banco de produção'),
    ({'RESTORE_PGDATABASE': ''}, 'RESTORE_PGDATABASE'),
    ({'AWS_ACCESS_KEY_ID': '005fake\n'}, 'quebra de linha'),
])
def test_restore_drill_refuses_unsafe_target(tmp_path, change, expected):
    env, log = _drill_env(tmp_path)
    env.update(change)
    result = _drill(env)
    assert result.returncode != 0 and expected in result.stderr
    assert not log.exists() or 'pg_restore' not in log.read_text()


def test_restore_drill_refuses_non_empty_target(tmp_path):
    env, log = _drill_env(tmp_path, tables='4')
    result = _drill(env)
    assert result.returncode != 0 and 'já tem 4 tabela(s)' in result.stderr
    assert 'restore' not in log.read_text() and 'pg_restore' not in log.read_text()


def test_backup_image_dispatches_only_known_modes():
    dockerfile = (ROOT / 'infra' / 'Dockerfile.railway-backup').read_text()
    for name in ('railway-backup-lib.sh', 'railway-backup.sh', 'railway-restore-drill.sh'):
        assert name in dockerfile
    assert 'backup) exec sh /railway-backup.sh' in dockerfile and 'restore-drill) exec sh /railway-restore-drill.sh' in dockerfile
