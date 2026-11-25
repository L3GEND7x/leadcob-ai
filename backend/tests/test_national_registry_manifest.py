import json
import pytest

from app.jobs import national_registry_manifest as job


def report(uf="AM", part=0, mode="preview", n=5):
    r = dict(uf=uf, part=part, mode=mode, release="2026-10",
             municipality_code=None, coverage_complete=False, eligible=n)
    if mode == "apply":
        r.update(created=2, existing=2, suppressed=1)
    return r


def test_persistent_plan_claim_and_resume(tmp_path):
    path = tmp_path / "manifest.sqlite"
    db = job.connect(path)
    job.init(db,"2026-10","preview",None,150000)
    assert job.summary(db)["counts"]["pending"] == 270
    a = job.claim(db)
    assert a[:2] == ("AM",0)
    other = job.connect(path)
    assert job.claim(other) is None
    with pytest.raises(RuntimeError):
        job.finish(other,("AM",0,"wrong-token"),report={"eligible":1})
    job.finish(db,a,report=job.validate_report(report(),"2026-10","preview","AM",0))
    db.close()
    job.init(other,"2026-10","preview",None,150000)
    assert job.summary(other)["totals"]["eligible"] == 5
    b = job.claim(other)
    assert b[:2] == ("AM",1)
    assert job.recover(other,"AM",1)
    assert job.claim(other,retry_failed=True)[:2] == ("AM",1)
    other.close()


def test_manifest_cannot_mix_releases_modes_or_sources(tmp_path):
    db = job.connect(tmp_path/"m.sqlite")
    job.init(db,"2026-10","preview",None,150000)
    for config in [("2026-09","preview",None,150000),
                   ("2026-10","apply",None,150000),
                   ("2026-10","preview","/different",150000),
                   ("2026-10","preview",None,300000)]:
        with pytest.raises(ValueError):
            job.init(db,*config)
    db.close()


def test_retry_limit_and_failed_state(tmp_path):
    db = job.connect(tmp_path/"m.sqlite")
    job.init(db,"2026-10","preview",None,150000)
    for i in range(3):
        cell = job.claim(db,"AM",retry_failed=True)
        assert cell[:2] == ("AM",0)
        job.finish(db,cell,failure="intake_failed")
    assert job.claim(db,"AM",retry_failed=True)[:2] == ("AM",1)
    assert job.summary(db)["counts"]["failed"] == 1
    db.close()


def test_report_requires_correct_scope_and_reconciled_counts():
    r = report(mode="apply")
    assert job.validate_report(r,"2026-10","apply","AM",0) == {
        "eligible":5,"created":2,"existing":2,"suppressed":1}
    for bad in [dict(r,created=3),dict(r,part=1),dict(r,eligible=True),
                dict(r,coverage_complete=True),dict(r,municipality_code="0255")]:
        with pytest.raises(ValueError):
            job.validate_report(bad,"2026-10","apply","AM",0)


def test_cli_bounded_preview_and_resume(tmp_path,monkeypatch):
    path = tmp_path/"m.sqlite"
    args = ["--manifest",str(path),"--release","2026-10","--uf","AM"]
    calls = []
    def fake(opts):
        calls.append(opts)
        assert "--apply" not in opts
        return report(part=int(opts[opts.index("--part")+1]))
    monkeypatch.setattr(job.intake,"main",fake)
    assert job.main(args+["--max-jobs","2"])["counts"]["succeeded"] == 2
    assert len(calls)==2
    assert job.main(args+["--status"])["counts"]["succeeded"] == 2
    assert len(calls)==2
    assert job.main(args)["counts"]["succeeded"] == 3
    assert calls[-1][calls[-1].index("--part")+1]=="2"
    with pytest.raises(SystemExit):
        job.main(args+["--apply"])


def test_cli_failure_stops_and_records_without_source_details(tmp_path,monkeypatch):
    path = tmp_path/"m.sqlite"
    def fail(opts):
        raise RuntimeError("sensitive source detail")
    monkeypatch.setattr(job.intake,"main",fail)
    args=["--manifest",str(path),"--release","2026-10","--max-jobs","3"]
    with pytest.raises(SystemExit):
        job.main(args)
    db=job.connect(path)
    assert job.summary(db)["counts"]==dict(pending=269,running=0,failed=1,succeeded=0)
    assert db.execute("SELECT failure FROM cells WHERE uf='AM' AND part=0").fetchone()[0]=="intake_failed"
    db.close()
