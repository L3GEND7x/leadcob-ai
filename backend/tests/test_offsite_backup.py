import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / 'infra' / 'offsite-backup.sh'


def run_backup(tmp_path, *, dump=True, stale=False, credentials=True, fail_check=False):
    backups = tmp_path / 'backups'
    backups.mkdir(exist_ok=True)
    if dump:
        dump_file = backups / 'leadcob-20261110T000000Z-abcdef.dump'
        dump_file.write_bytes(b'verified dump')
        if stale:
            os.utime(dump_file, (1000000000, 1000000000))
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / 'restic'
    fake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$RESTIC_TEST_LOG"\n'
                    + ('[ "$1" != check ]\n' if fail_check else 'exit 0\n'))
    fake.chmod(0o755)
    log = tmp_path / 'restic.log'
    env = {**os.environ, 'PATH': f'{bin_dir}:{os.environ["PATH"]}',
           'BACKUP_DIR': str(backups), 'RESTIC_TEST_LOG': str(log),
           'RESTIC_REPOSITORY': 's3:https://s3.example.com/private-backup',
           'RESTIC_PASSWORD': 'test-password', 'AWS_ACCESS_KEY_ID': 'test-key',
           'AWS_SECRET_ACCESS_KEY': 'test-secret'}
    if not credentials:
        env.pop('RESTIC_PASSWORD')
    result = subprocess.run(['sh', str(SCRIPT), '--once'], env=env, capture_output=True, text=True)
    return result, log.read_text() if log.exists() else ''


def test_offsite_requires_recent_dump_and_credentials(tmp_path):
    result, calls = run_backup(tmp_path, dump=False)
    assert result.returncode != 0 and not calls
    result, calls = run_backup(tmp_path, stale=True)
    assert result.returncode != 0 and not calls
    result, calls = run_backup(tmp_path, credentials=False)
    assert result.returncode != 0 and not calls


def test_offsite_backup_checks_repository_and_propagates_failure(tmp_path):
    result, calls = run_backup(tmp_path)
    assert result.returncode == 0
    assert 'backup ' in calls and 'check' in calls
    assert '.leadcob-*' in calls
    result, calls = run_backup(tmp_path, fail_check=True)
    assert result.returncode != 0 and 'check' in calls
