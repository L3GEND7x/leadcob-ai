from datetime import date
import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.services.asaas_sandbox_bindings import verify_bound_invoice


def test_bound_verification_is_tenant_scoped_and_read_only():
    engine = create_engine("sqlite://")
    with Session(engine) as session:
        for ddl in (
            "CREATE TABLE commercial_invoices (id INTEGER PRIMARY KEY, organization_id INTEGER, amount_cents INTEGER, status TEXT)",
            "CREATE TABLE asaas_sandbox_customers (organization_id INTEGER PRIMARY KEY, customer_id TEXT)",
            "CREATE TABLE asaas_sandbox_payments (invoice_id INTEGER PRIMARY KEY, payment_id TEXT, external_reference TEXT)",
            "INSERT INTO commercial_invoices VALUES (1, 10, 2700, 'open')",
            "INSERT INTO asaas_sandbox_customers VALUES (10, 'cus_10')",
            "INSERT INTO asaas_sandbox_payments VALUES (1, 'pay_1', 'invoice-1')",
        ):
            session.execute(text(ddl))
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json=dict(
                id="pay_1", customer="cus_10", externalReference="invoice-1",
                value=27, status="RECEIVED", deleted=False, refunds=[],
                paymentDate=date.today().isoformat(), billingType="PIX"))
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            assert not verify_bound_invoice(session, 20, 1, "test", client)
            assert not calls
            assert verify_bound_invoice(session, 10, 1, "test", client)
            assert len(calls) == 1
            assert session.execute(text("SELECT status FROM commercial_invoices")).scalar_one() == "open"
            session.execute(text("UPDATE commercial_invoices SET status='void'"))
            assert not verify_bound_invoice(session, 10, 1, "test", client)
            assert len(calls) == 1
