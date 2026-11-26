"""Manual institutional discovery: authenticated HTTP, one job per click, no network in tests."""
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core import security
from app.core.config import settings
from app.db.database import Base, get_db
from app.db.models import Company, BusinessContact, AuditLog, Suppression, ContactDiscoveryItem
from app.api import routes_contacts as contacts
from app.services.cnpj import _dv, WEIGHTS_1, WEIGHTS_2
from app.services.contact_discovery_queue import enqueue, progress


def _cnpj(seed):
    base=f"{seed:012d}"
    d1=_dv(base, WEIGHTS_1)
    return base+d1+_dv(base+d1, WEIGHTS_2)


def test_manual_discovery_requires_owner_csrf_and_processes_one_selected_job(tmp_path, monkeypatch):
    engine=create_engine(f"sqlite:///{tmp_path / 'manual-queue.sqlite'}",
                         connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session=sessionmaker(bind=engine)
    def override_db():
        with Session() as db:
            yield db
    app.dependency_overrides[get_db]=override_db
    monkeypatch.setattr(security,"SessionLocal",Session)
    monkeypatch.setattr(settings,"admin_password_hash",security.password_hash("owner-strong-test-password"))
    monkeypatch.setattr(settings,"admin_username","owner-"+uuid4().hex)
    monkeypatch.setattr(settings,"app_env","development")
    monkeypatch.setattr(settings,"public_url","")
    monkeypatch.setattr(settings,"contact_discovery_worker_enabled",False)
    with Session() as db:
        db.add_all([
            Company(id=11,name="Fixture LTDA",cnpj=_cnpj(11),state="AM",
                    city="Manaus",registration_status="ATIVA",legal_nature="Sociedade Empresária Limitada",website="https://example.com"),
            Company(id=12,name="Empresa suprimida",cnpj=_cnpj(12),state="AM",
                    city="Manaus",registration_status="ATIVA",legal_nature="Sociedade Empresária Limitada",website="https://example.com"),
            Company(id=13,name="Outra fila",cnpj=_cnpj(13),state="AM",
                    city="Manaus",registration_status="ATIVA",legal_nature="Sociedade Empresária Limitada",website="https://example.org"),
        ])
        db.flush()
        db.add(Suppression(company_id=12,reason="opt-out teste"))
        db.commit()
        first_job=enqueue(db,[11,12])
        other_job=enqueue(db,[13])
        other_item=db.query(ContactDiscoveryItem).filter_by(job_id=other_job).one()
        other_item.attempts=3  # unrelated exhausted row must not be mutated by this job
        db.commit()
    called=[]
    from app.collectors import site_contacts
    def source(website, max_pages=2):
        called.append(website)
        assert website=="https://example.com" and max_pages==2
        return {"emails":[{"email":"contato@example.com","source_url":"https://example.com"}],
                "channels":[],"pages_read":["https://example.com"],"notes":[]}
    monkeypatch.setattr(site_contacts,"discover",source)
    url=f"/api/contacts/discovery-jobs/{first_job}/process-one"
    client=TestClient(app)
    try:
        assert client.post(url,json={}).status_code==401
        login=client.post("/api/auth/login",json={
            "username":settings.admin_username,"password":"owner-strong-test-password"})
        assert login.status_code==200,login.text
        headers={"origin":"http://testserver","x-csrf-token":login.json()["csrf_token"]}
        assert client.post(url,json={}).status_code==403
        assert client.post(url,headers={**headers,"origin":"https://evil.example"},json={}).status_code==403
        assert client.post("/api/contacts/discovery-jobs/99999/process-one",headers=headers,json={}).status_code==404
        result=client.post(url,headers=headers,json={})
        assert result.status_code==200,result.text
        assert result.json()["attempted"] is True
        assert result.json()["job"]["completed"]==1
        assert result.json()["job"]["queued"]==1
        assert called==["https://example.com"]
        second=client.post(url,headers=headers,json={})
        assert second.status_code==200,second.text
        assert second.json()["job"]["skipped"]==1
        assert called==["https://example.com"]  # suppressed company never fetched
        third=client.post(url,headers=headers,json={})
        assert third.status_code==200 and third.json()["attempted"] is False
        assert called==["https://example.com"]
        with Session() as db:
            assert progress(db,other_job)["queued"]==1
            records=list(db.scalars(select(BusinessContact)))
            assert len(records)==1
            assert records[0].value=="contato@example.com"
            assert records[0].status=="a_verificar"
            assert db.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.event=="discovery_manual_step"))==3
    finally:
        client.close()
        app.dependency_overrides.pop(get_db,None)
        engine.dispose()


def test_manual_worker_process_lock_returns_429_when_busy(tmp_path,monkeypatch):
    from fastapi import HTTPException
    from sqlalchemy.orm import Session
    from app.db.models import ContactDiscoveryJob
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    class Busy:
        def acquire(self,blocking):
            assert blocking is False
            return False
    monkeypatch.setattr(contacts,"_manual_contact_step_lock",Busy())
    with Session(engine) as db:
        job=ContactDiscoveryJob()
        db.add(job);db.commit()
        try:
            contacts.manually_process_contact_job(job.id,db)
            assert False, "Must reject concurrent request"
        except HTTPException as exc:
            assert exc.status_code==429
    engine.dispose()
