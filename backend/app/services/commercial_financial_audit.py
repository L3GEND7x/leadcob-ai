"""Owner-only, read-only internal financial audit. Never treats sandbox as settled cash."""
from collections import Counter
from datetime import date, datetime, timezone
from sqlalchemy import select, func
from fastapi import HTTPException
from app.db.models import (Organization, CommercialInvoice, CommercialPlan,
    CommercialSubscription, CommercialRenewal, AsaasSandboxPayment,
    AsaasSandboxIssueReservation)
from app.core.security import stamp

MAX_ROWS = 5000


def audit(db, organization_id, today=None):
    """Report ledger state without payment-provider calls or mutations."""
    if not db.get(Organization, organization_id):
        raise HTTPException(404, "Organização não encontrada.")
    today = today or datetime.now(timezone.utc).date()
    if not isinstance(today, date):
        raise ValueError("Data de corte inválida.")
    total = db.scalar(select(func.count(CommercialInvoice.id)).where(
        CommercialInvoice.organization_id == organization_id)) or 0
    if total > MAX_ROWS:
        raise HTTPException(422, "Quantidade de recebíveis supera o limite de auditoria. Use exportação controlada.")
    invoices = list(db.scalars(select(CommercialInvoice).where(
        CommercialInvoice.organization_id == organization_id).order_by(CommercialInvoice.id)))
    ids = [x.id for x in invoices]
    plans = {x.id: x for x in db.scalars(select(CommercialPlan).where(
        CommercialPlan.id.in_({x.plan_id for x in invoices})))}
    bindings = {x.invoice_id: x for x in db.scalars(select(AsaasSandboxPayment).where(
        AsaasSandboxPayment.invoice_id.in_(ids)))}
    reservations = {x.invoice_id: x for x in db.scalars(select(AsaasSandboxIssueReservation).where(
        AsaasSandboxIssueReservation.invoice_id.in_(ids)))}
    renewals = {x.invoice_id: x for x in db.scalars(select(CommercialRenewal).where(
        CommercialRenewal.invoice_id.in_(ids)))}
    sums = dict(open_cents=0, overdue_open_cents=0, manual_paid_cents=0,
        sandbox_associated_open_cents=0, void_cents=0)
    counts = Counter()
    exceptions = []
    for item in invoices:
        flags = []
        binding, reservation = bindings.get(item.id), reservations.get(item.id)
        linked = binding is not None or reservation is not None
        renewed = renewals.get(item.id)
        plan = plans.get(item.plan_id)
        amount = item.amount_cents
        if item.status == "open":
            sums["open_cents"] += amount
            counts["open"] += 1
            if item.due_date < today.isoformat():
                sums["overdue_open_cents"] += amount
                counts["overdue_open"] += 1
            if linked:
                sums["sandbox_associated_open_cents"] += amount
            if item.payment_reference or item.paid_at:
                flags.append("open_with_settlement_metadata")
        elif item.status == "paid":
            counts["paid"] += 1
            if linked:
                flags.append("sandbox_marked_paid")
            else:
                sums["manual_paid_cents"] += amount
            if not item.payment_reference or not item.paid_at:
                flags.append("paid_without_manual_evidence")
        elif item.status == "void":
            counts["void"] += 1
            sums["void_cents"] += amount
            if item.payment_reference or item.paid_at:
                flags.append("void_with_settlement_metadata")
            if linked:
                flags.append("void_with_sandbox_association")
        else:
            flags.append("unknown_ledger_status")
        if plan is None:
            flags.append("missing_plan")
        elif plan.monthly_price_cents != amount:
            # An old invoice may legitimately have a historical plan price.
            flags.append("plan_current_price_differs_from_invoice")
        if reservation and (reservation.amount_cents != amount or reservation.due_date != item.due_date):
            flags.append("sandbox_reservation_amount_or_date_conflict")
        if binding and reservation and binding.external_reference != reservation.external_reference:
            flags.append("sandbox_binding_reservation_conflict")
        if reservation and not binding:
            flags.append("sandbox_unresolved_reservation")
        if renewed:
            if renewed.organization_id != organization_id or item.status != "paid" or linked:
                flags.append("renewal_without_eligible_payment")
            sub = db.get(CommercialSubscription, organization_id)
            if sub is None:
                flags.append("renewal_without_subscription")
            elif stamp(sub.ends_at) < stamp(renewed.new_end):
                flags.append("subscription_ends_before_recorded_renewal")
        if flags:
            counts["invoices_with_flags"] += 1
            exceptions.append({"invoice_id":item.id,"flags":flags,
                "amount_cents":amount,"status":item.status,
                "sandbox_associated":linked})
    sub = db.get(CommercialSubscription, organization_id)
    return {"organization_id":organization_id,"as_of":today.isoformat(),
        "receivables":total,"counts":dict(counts),"amounts_cents":sums,
        "exceptions":exceptions,"exception_count":len(exceptions),
        "subscription_recorded":sub is not None,
        "provider_verified":False,"bank_reconciled":False,
        "production_payments_enabled":False,
        "note":"Diagnóstico do livro interno: baixa manual não comprova depósito bancário; "
               "sandbox não comprova receita real. Conflitos não são corrigidos automaticamente."}
