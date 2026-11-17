"""Read-only provider observations; never settle the local ledger."""
from decimal import Decimal, InvalidOperation
from sqlalchemy import text
from app.services.asaas_reconciliation import fetch_payment, verify_payment


def cents(value):
    try:
        amount = Decimal(str(value)) * 100
        if amount.is_finite() and amount == amount.to_integral_value() and 0 <= amount <= 2147483647:
            return int(amount)
    except (InvalidOperation, TypeError, ValueError):
        pass
    return None


def classify(data, binding):
    raw_status = data.get("status")
    status = raw_status if isinstance(raw_status, str) and len(raw_status) <= 80 else "UNKNOWN"
    gross = cents(data.get("value"))
    net = cents(data.get("netValue"))
    if (data.get("id") != binding["payment_id"]
            or data.get("customer") != binding["customer_id"]
            or data.get("externalReference") != binding["external_reference"]
            or gross != binding["amount_cents"]
            or data.get("billingType") not in {"PIX", "BOLETO"}):
        outcome = "divergence"
    elif status in {"CHARGEBACK_REQUESTED", "CHARGEBACK_DISPUTE", "AWAITING_CHARGEBACK_REVERSAL"}:
        outcome = "chargeback_review"
    elif status in {"REFUNDED", "REFUND_REQUESTED", "REFUND_IN_PROGRESS", "PARTIALLY_REFUNDED"} or data.get("refunds"):
        outcome = "refund_review"
    elif data.get("deleted") is True:
        outcome = "deleted_review"
    elif data.get("deleted") is not False:
        outcome = "divergence"
    elif verify_payment(data, payment_id=binding["payment_id"],
                        external_reference=binding["external_reference"],
                        customer_id=binding["customer_id"], amount_cents=binding["amount_cents"]):
        outcome = "sandbox_received" if net is not None and net <= gross else "financial_review"
    elif status in {"PENDING", "OVERDUE", "CONFIRMED", "AWAITING_RISK_ANALYSIS"}:
        outcome = "not_received"
    else:
        outcome = "financial_review"
    return dict(outcome=outcome, provider_status=status, gross_cents=gross, net_cents=net)


def event_binding(db, organization_id, invoice_id, event_id):
    return db.execute(text("""
        SELECT e.event_id, p.payment_id, p.external_reference, c.customer_id, i.amount_cents
        FROM asaas_sandbox_events e
        JOIN asaas_sandbox_payments p ON p.payment_id=e.payment_id
        JOIN commercial_invoices i ON i.id=p.invoice_id
        JOIN asaas_sandbox_customers c ON c.organization_id=i.organization_id
        WHERE i.id=:iid AND i.organization_id=:oid AND e.event_id=:eid
    """), {"iid": invoice_id, "oid": organization_id, "eid": event_id}).mappings().one_or_none()


def observe(binding, api_key, client=None):
    data = fetch_payment(binding["payment_id"], api_key, client)
    return classify(data, binding)
