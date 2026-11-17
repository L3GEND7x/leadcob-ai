"""Internal sandbox binding and verification. No writes to the financial ledger."""
from sqlalchemy import text
from app.services.asaas_reconciliation import fetch_payment, verify_payment


def verify_bound_invoice(session, organization_id, invoice_id, api_key, client=None):
    """Only verify against server-side persisted identities and invoice value.

    Returns False for missing/cross-tenant bindings or non-open invoices.
    Provider failures propagate; the caller must never interpret them as paid.
    """
    row = session.execute(text("""
        SELECT i.amount_cents, c.customer_id, p.payment_id, p.external_reference
        FROM commercial_invoices AS i
        JOIN asaas_sandbox_customers AS c ON c.organization_id = i.organization_id
        JOIN asaas_sandbox_payments AS p ON p.invoice_id = i.id
        WHERE i.id = :invoice_id AND i.organization_id = :organization_id
          AND i.status = 'open'
    """), {"invoice_id": invoice_id, "organization_id": organization_id}).mappings().one_or_none()
    if row is None:
        return False
    data = fetch_payment(row["payment_id"], api_key, client)
    return verify_payment(data, payment_id=row["payment_id"],
                          external_reference=row["external_reference"],
                          customer_id=row["customer_id"], amount_cents=row["amount_cents"])
