"""Versioned schema must be created before production serves requests."""
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[2]


def test_initial_revision_and_upgrade_idempotence(tmp_path):
    db = tmp_path / 'new.db'
    env = {**os.environ, 'PYTHONPATH': str(ROOT / 'backend'), 'DATABASE_URL': f'sqlite:///{db}'}
    command = [sys.executable, '-m', 'alembic', '-c', str(ROOT / 'alembic.ini')]
    subprocess.run([*command, 'upgrade', 'head'], cwd=ROOT, env=env, check=True)
    engine = create_engine(env['DATABASE_URL'])
    assert {'companies', 'portfolio_items', 'assistant_conversations', 'alembic_version'} <= set(inspect(engine).get_table_names())
    with engine.begin() as connection:
        revision = connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        connection.execute(text("INSERT INTO companies (name, created_at) VALUES ('Registro preservado', CURRENT_TIMESTAMP)"))
    assert revision == '2b3f641847d9'
    subprocess.run([*command, 'upgrade', 'head'], cwd=ROOT, env=env, check=True)
    subprocess.run([*command, 'check'], cwd=ROOT, env=env, check=True)
    with engine.connect() as connection:
        assert connection.execute(text('SELECT name FROM companies WHERE name = :name'),
                                  {'name': 'Registro preservado'}).scalar_one() == 'Registro preservado'


def test_production_check_refuses_unversioned_schema(tmp_path):
    db = tmp_path / 'unversioned.db'
    env = {**os.environ, 'PYTHONPATH': str(ROOT / 'backend'), 'DATABASE_URL': f'sqlite:///{db}'}
    code = ('from app.db.database import check_schema_revision; '
            'check_schema_revision()')
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env,
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert 'sem versão' in result.stderr
