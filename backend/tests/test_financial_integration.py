"""Isolated HTTP regression tests; provider calls explicitly replaced by test doubles."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from threading import Barrier
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.core import security
from app.core.config import settings
from app.db.database import Base
from app.db.models import (Organization, CommercialPlan, CommercialSubscription, CommercialInvoice,
    CommercialRenewal, AsaasSandboxCustomer, AsaasSandboxIssueReservation, AuditLog)
from app.api import routes_commercial_admin as admin
from app.services.asaas_reconciliation import PaymentUnavailable


@pytest.fixture
def billing(tmp_path, monkeypatch, request):
    url = os.environ.get("LEADCOB_TEST_POSTGRES_URL")
    schema = None
    if url:
        parsed = make_url(url)
        if parsed.get_backend_name() != "postgresql" or parsed.host not in {"localhost", "127.0.0.1"} or parsed.database != "leadcob_test":
            raise RuntimeError("Use only a local dedicated leadcob_test PostgreSQL database")
        schema = "test_" + uuid4().hex
        maintenance = create_engine(url)
        with maintenance.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA {schema}"))
        maintenance.dispose()
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'billing.db'}",
                               connect_args={"check_same_thread": False, "timeout": 30})
    def cleanup():
        engine.dispose()
        if schema:
            maintenance = create_engine(url)
            try:
                with maintenance.begin() as conn:
                    conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            finally:
                maintenance.dispose()
    request.addfinalizer(cleanup)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(admin, "SessionLocal", session)
    monkeypatch.setattr(security, "SessionLocal", session)
    monkeypatch.setattr(settings, "admin_password_hash", security.password_hash("owner-test-password-128"))
    monkeypatch.setattr(settings, "admin_username", "audit-" + uuid4().hex)
    monkeypatch.setattr(settings, "public_url", "")
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "asaas_sandbox_api_key", "test-not-a-real-key")
    now = datetime.now(timezone.utc)
    start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    from calendar import monthrange
    y, m = (start.year + 1, 1) if start.month == 12 else (start.year, start.month + 1)
    end = start.replace(year=y, month=m, day=min(start.day, monthrange(y, m)[1]))
    with session() as db:
        a = Organization(name="A", slug="a", active=True)
        b = Organization(name="B", slug="b", active=True)
        plan = CommercialPlan(code="test", name="Test", monthly_price_cents=2700,
            max_members=1,max_leads=1,max_contacts=1,max_tasks=1,max_portfolios=1,max_titles=1,active=True)
        db.add_all([a,b,plan]); db.flush()
        oid, other, pid = a.id,b.id,plan.id
        db.add(CommercialSubscription(organization_id=oid,plan_id=pid,
            starts_at=start-timedelta(days=30),ends_at=start,status="active"))
        db.add(AsaasSandboxCustomer(organization_id=oid,customer_id="cus_test"))
        db.commit()
    # No lifespan: isolated schema above, no development seed or external services.
    # TestClient without context does not run startup against the global database.
    c = TestClient(app)
    login = c.post("/api/auth/login",json={"username":settings.admin_username,"password":"owner-test-password-128"})
    assert login.status_code == 200, login.text
    headers = {"Origin":"http://testserver","X-CSRF-Token":login.json()["csrf_token"]}
    path = f"/api/owner/commercial/organizations/{oid}/invoices"
    payload = dict(plan_id=pid,period_start=start.date().isoformat(),period_end=end.date().isoformat(),
                   due_date=start.date().isoformat())
    try:
        yield c, headers, path, payload, session, oid, other, end
    finally:
        c.close()


def create_receivable(c, headers, path, payload):
    r = c.post(path,headers=headers,json=payload)
    assert r.status_code == 201,r.text
    return r.json()["id"]


def test_renewal_once_and_cross_tenant(billing):
    c,h,path,payload,session,oid,other,end = billing
    iid = create_receivable(c,h,path,payload)
    renew = f"{path}/{iid}/renew"
    assert c.post(renew,headers=h).status_code == 409
    assert c.post(renew.replace(f"/organizations/{oid}/",f"/organizations/{other}/"),headers=h).status_code == 404
    paid = c.post(f"{path}/{iid}/settle",headers=h,json=dict(amount_cents=2700,
                  payment_reference="bank-test-reference",paid_at=datetime.now(timezone.utc).isoformat()))
    assert paid.status_code == 200,paid.text
    assert c.post(renew).status_code == 403
    first = c.post(renew,headers=h)
    assert first.status_code == 200,first.text
    assert first.json()["replayed"] is False
    replay = c.post(renew,headers=h)
    assert replay.status_code == 200,replay.text
    assert replay.json()["replayed"] is True
    with session() as db:
        assert db.scalar(select(func.count()).select_from(CommercialRenewal)) == 1
        assert db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.event=="commercial_subscription_renewed")) == 1
        assert security.stamp(db.get(CommercialSubscription,oid).ends_at) == end


def test_uncertain_issue_is_not_repeated_and_blocks_renewal(billing, monkeypatch):
    c,h,path,payload,session,oid,other,end = billing
    iid = create_receivable(c,h,path,payload)
    issue = f"{path}/{iid}/asaas-sandbox/issue"
    calls = []
    def uncertain(**kwargs):
        calls.append(kwargs)
        raise PaymentUnavailable("timeout")
    monkeypatch.setattr(admin,"issue_charge",uncertain)
    assert c.post(issue,headers=h,json={"billing_type":"PIX"}).status_code == 503
    assert c.post(issue,headers=h,json={"billing_type":"PIX"}).status_code == 409
    assert len(calls) == 1
    with session() as db:
        assert db.get(AsaasSandboxIssueReservation,iid) is not None
        assert db.get(CommercialInvoice,iid).status == "open"
    paid = c.post(f"{path}/{iid}/settle",headers=h,json=dict(amount_cents=2700,
                  payment_reference="manual-test-reference",paid_at=datetime.now(timezone.utc).isoformat()))
    assert paid.status_code == 409,paid.text
    assert c.post(f"{path}/{iid}/void",headers=h).status_code == 409
    assert c.post(f"{path}/{iid}/renew",headers=h).status_code == 409
    with session() as db:
        assert db.get(CommercialInvoice,iid).status == "open"


def test_concurrent_invoice_creation(billing):
    c,h,path,payload,session,oid,other,end = billing
    barrier = Barrier(2)
    cookies = dict(c.cookies)
    def attempt():
        client = TestClient(app,cookies=cookies)
        try:
            barrier.wait(timeout=10)
            response = client.post(path,headers=h,json=payload)
            assert response.status_code == 201,response.text
            return response.json()["id"]
        finally:
            client.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a,b = [pool.submit(attempt) for _ in range(2)]
        assert a.result(timeout=30) == b.result(timeout=30)
    with session() as db:
        assert db.scalar(select(func.count()).select_from(CommercialInvoice)) == 1


def test_bound_sandbox_cannot_settle_or_void(billing, monkeypatch):
    c,h,path,payload,session,oid,other,end = billing
    iid=create_receivable(c,h,path,payload)
    monkeypatch.setattr(admin,"issue_charge",lambda **kwargs:"pay_fixture")
    response=c.post(f"{path}/{iid}/asaas-sandbox/issue",headers=h,json={"billing_type":"BOLETO"})
    assert response.status_code==201,response.text
    assert c.post(f"{path}/{iid}/settle",headers=h,json=dict(amount_cents=2700,
        payment_reference="fixture-bank",paid_at=datetime.now(timezone.utc).isoformat())).status_code==409
    assert c.post(f"{path}/{iid}/void",headers=h).status_code==409
    assert c.post(f"{path}/{iid}/renew",headers=h).status_code==409
    with session() as db:
        assert db.get(CommercialInvoice,iid).status=="open"
