from contextlib import nullcontext
import pytest
from app.jobs import capture_pncp as job
from app.collectors import pncp


@pytest.mark.parametrize('status, exit_code', [('completed', 0), ('partial', 2), ('failed', 1)])
def test_scheduler_exposes_capture_status(monkeypatch, status, exit_code, capsys):
    monkeypatch.setattr(job, 'check_schema_revision', lambda: None)
    monkeypatch.setattr(job, 'SessionLocal', lambda: nullcontext(object()))
    def capture(**kw):
        assert kw['days'] == 3 and kw['max_pages'] == 2
        return dict(run_id=1, status=status, pages_read=1, created=0, updated=0, proven=0)
    monkeypatch.setattr(job, 'capture_pncp', capture)
    if exit_code:
        with pytest.raises(SystemExit) as exc:
            job.main(['--days','3','--max-pages','2'])
        assert exc.value.code == exit_code
    else:
        job.main(['--days','3','--max-pages','2'])
    assert f'"status": "{status}"' in capsys.readouterr().out


def test_probe_never_opens_database(monkeypatch, capsys):
    def forbidden():
        pytest.fail('Probe must not open database or check schema')
    monkeypatch.setattr(job, 'check_schema_revision', forbidden)
    monkeypatch.setattr(job, 'SessionLocal', forbidden)
    monkeypatch.setattr(pncp, 'scan_publications', lambda **kw: dict(pages_read=6,
        records_read=0,total_available=0,coverage_complete=True,date_from='2026-11-24',date_to='2026-11-26',errors=[]))
    job.main(['--probe'])
    assert '"database_written": false' in capsys.readouterr().out
