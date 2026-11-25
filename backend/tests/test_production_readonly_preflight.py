from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import Company
from app.jobs import production_readonly_preflight as job


def test_preflight_no_customer_rows_in_report(monkeypatch):
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Company(name="Private synthetic company",state="AM",city="Manaus"))
        db.commit()
        monkeypatch.setattr(job,"assistant_status",lambda **kw:{"configured":True,"configuration_checks":dict.fromkeys(
            ("api_key","model","monthly_budget","input_price","output_price"),True)})
        monkeypatch.setattr(job,"readiness",lambda *a:{"configuration_checks":dict.fromkeys(
            ("production_mode","postgresql","https_origin","owner_auth_configured","demo_disabled","schema_tables_present"),True)})
        r=job.audit(db)
        assert r["checks_passed"],r
        assert "Private synthetic company" not in str(r)
        assert r["authenticated_http_tested"] is False
        assert r["provider_generation_tested"] is False
        assert r["production_release_ready"] is False
        assert next(c for c in r["checks"] if c["check"]=="registry")["metrics"]["company_records"]==1
    engine.dispose()


def test_preflight_does_not_log_internal_exception(monkeypatch):
    def fail(*args,**kw):
        raise RuntimeError("private details")
    monkeypatch.setattr(job,"registry_coverage",fail)
    r=job.audit(None)
    assert not r["checks_passed"]
    assert "private details" not in str(r)
