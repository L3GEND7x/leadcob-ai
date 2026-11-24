"""Worker release gates: no network contact collection without explicit opt-in."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import json
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import ContactWorkerHeartbeat
from app.jobs import discover_contacts as worker
from app.services.contact_discovery_queue import record_heartbeat, prune_heartbeats, enqueue


def test_disabled_worker_does_not_access_queue_or_network(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["worker"])
    monkeypatch.setattr(worker.settings, "app_env", "production")
    monkeypatch.setattr(worker.settings, "contact_discovery_worker_enabled", False)
    calls = []
    monkeypatch.setattr(worker, "check_schema_revision", lambda: calls.append("schema"))
    def deny_session():
        raise AssertionError("Disabled worker must not open a database session")
    monkeypatch.setattr(worker, "SessionLocal", deny_session)
    monkeypatch.setattr(worker, "process", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("Disabled worker must not process any company")))
    worker.main()
    assert calls == ["schema"]


def test_probe_only_reads_aggregate_metrics_without_processing(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["worker", "--probe"])
    monkeypatch.setattr(worker.settings, "app_env", "development")
    monkeypatch.setattr(worker.settings, "contact_discovery_worker_enabled", False)
    obj = object()
    monkeypatch.setattr(worker, "SessionLocal", lambda: nullcontext(obj))
    monkeypatch.setattr(worker, "diagnostics", lambda db: {
        "counts": {"queued": 17, "running": 0, "completed": 1, "failed": 0, "skipped": 0},
        "expired_leases": 0, "worker_verified": False, "recent_workers": 0,
        "private_contact_value": "must-not-appear"})
    monkeypatch.setattr(worker, "process", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("Probe must never process or access company sites")))
    worker.main()
    report = json.loads(capsys.readouterr().out)
    assert report["counts"]["queued"] == 17
    assert report["collection_attempted"] is False
    assert "private_contact_value" not in report


def test_enabled_worker_prunes_heartbeats_and_runs_bounded(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["worker", "--max-items", "3"])
    monkeypatch.setattr(worker.settings, "app_env", "development")
    monkeypatch.setattr(worker.settings, "contact_discovery_worker_enabled", True)
    obj = object()
    monkeypatch.setattr(worker, "SessionLocal", lambda: nullcontext(obj))
    calls = []
    monkeypatch.setattr(worker, "prune_heartbeats", lambda db: calls.append("pruned"))
    monkeypatch.setattr(worker, "record_heartbeat", lambda db, worker_id, state, processed:
                        calls.append((state, processed)))
    monkeypatch.setattr(worker.signal, "signal", lambda *args: None)
    def fake_process(stop, max_items, continuous, idle_seconds, interval_seconds, heartbeat):
        assert max_items == 3 and continuous is False
        heartbeat("processing", 0)
        heartbeat("idle", 3)
        return 3
    monkeypatch.setattr(worker, "process", fake_process)
    worker.main()
    assert calls[0] == "pruned"
    assert calls[1][0] == "starting"
    assert calls[-1] == ("stopped", 3)


def test_pruning_only_removes_expired_worker_heartbeats():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        job_id = enqueue(db, [999])
        record_heartbeat(db, "old", "stopped", 2, now - timedelta(days=31))
        record_heartbeat(db, "fresh", "idle", 0, now)
        assert prune_heartbeats(db, now, retention_days=30) == 1
        assert db.get(ContactWorkerHeartbeat, "old") is None
        assert db.get(ContactWorkerHeartbeat, "fresh") is not None
        from app.services.contact_discovery_queue import progress
        assert progress(db, job_id)["queued"] == 1
    engine.dispose()


def test_probe_coverage_reports_only_aggregate_manaus_data(monkeypatch, capsys):
    from app.services import registry_coverage as registry_module
    from app.api import routes_contacts
    monkeypatch.setattr(sys, "argv", ["worker", "--probe", "--probe-coverage"])
    monkeypatch.setattr(worker.settings, "app_env", "development")
    monkeypatch.setattr(worker.settings, "contact_discovery_worker_enabled", False)
    monkeypatch.setattr(worker, "SessionLocal", lambda: nullcontext(object()))
    monkeypatch.setattr(worker, "diagnostics", lambda db: {
        "counts": {"queued": 0}, "expired_leases": 0,
        "worker_verified": False, "recent_workers": 0})
    expected_registry={
        "company_records": 10, "unique_valid_cnpjs": 8, "active_cnpjs": 7,
        "duplicate_valid_records": 1, "missing_cnpj_records": 1,
        "invalid_cnpj_records": 0, "conflicting_status_cnpjs": 0,
        "with_registry_source_and_date": 7, "with_target_profile": 7,
        "secret_company_name": "never-output"}
    def registry(db, uf, city):
        assert (uf,city)==("AM","Manaus")
        return expected_registry
    def contacts(*,uf,city,db):
        assert (uf,city)==("AM","Manaus")
        return {"eligible_company_records": 10, "with_any_channel": 3,
            "with_any_verified_channel": 1,
            "channels": {"email":{"available":3,"verified":1}},
            "private_email":"never-output"}
    monkeypatch.setattr(registry_module, "registry_coverage", registry)
    monkeypatch.setattr(routes_contacts, "contact_coverage", contacts)
    worker.main()
    report=json.loads(capsys.readouterr().out)
    assert report["manaus_registry"]["unique_valid_cnpjs"] == 8
    assert report["manaus_contact_coverage"]["with_any_channel"] == 3
    assert report["collection_attempted"] is False
    assert "never-output" not in str(report)
