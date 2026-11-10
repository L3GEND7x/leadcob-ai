"""The backup must never publish a failed or incomplete dump."""
import os
import subprocess
from pathlib import Path


def test_backup_is_atomic_and_keeps_previous_dump_on_failure(tmp_path):
    root = Path(__file__).resolve().parents[2]
    backup_dir = tmp_path / 'backups'
    backup_dir.mkdir()
    previous = backup_dir / 'leadcob-previous.dump'
    previous.write_bytes(b'previous-good-backup')
    shims = tmp_path / 'bin'
    shims.mkdir()
    dump = shims / 'pg_dump'
    dump.write_text('#!/bin/sh\ncase "$2" in --file=*) printf dump > "${2#--file=}";; *) exit 1;; esac\n')
    restore = shims / 'pg_restore'
    restore.write_text('#!/bin/sh\n[ "${BACKUP_FAIL:-}" != 1 ] && [ -s "$2" ]\n')
    dump.chmod(0o700)
    restore.chmod(0o700)
    env = {**os.environ, 'PATH': str(shims) + os.pathsep + os.environ['PATH'],
           'BACKUP_DIR': str(backup_dir), 'BACKUP_FAIL': '1'}
    script = root / 'infra' / 'backup.sh'
    failed = subprocess.run(['sh', str(script), '--once'], env=env, capture_output=True, text=True)
    assert failed.returncode != 0
    assert previous.read_bytes() == b'previous-good-backup'
    assert list(backup_dir.glob('leadcob-*.dump')) == [previous]
    assert not list(backup_dir.glob('.leadcob-*'))

    env['BACKUP_FAIL'] = '0'
    good = subprocess.run(['sh', str(script), '--once'], env=env, capture_output=True, text=True)
    assert good.returncode == 0, good.stderr
    new = Path(good.stdout.strip())
    assert new.exists() and new.read_bytes() == b'dump'
    assert previous.read_bytes() == b'previous-good-backup'
    assert not list(backup_dir.glob('.leadcob-*'))
