"""Conservative owner-approved renewal of an existing subscription."""
from datetime import date, datetime, time, timezone
from app.core.security import stamp


class RenewalRejected(ValueError):
    pass


def renewal_end(subscription, invoice, plan, now):
    if (subscription is None or invoice is None or plan is None
            or subscription.status != "active" or not plan.active
            or subscription.organization_id != invoice.organization_id
            or subscription.plan_id != invoice.plan_id or plan.id != invoice.plan_id
            or invoice.amount_cents <= 0 or invoice.status != "paid"
            or not invoice.payment_reference or not invoice.paid_at
            or stamp(invoice.paid_at) > now):
        raise RenewalRejected("Assinatura ou recebível indisponível.")
    try:
        start = datetime.combine(date.fromisoformat(invoice.period_start), time.min, timezone.utc)
        end = datetime.combine(date.fromisoformat(invoice.period_end), time.min, timezone.utc)
    except (TypeError, ValueError) as exc:
        raise RenewalRejected("Período inválido.") from exc
    if start != stamp(subscription.ends_at) or end <= start or end <= now:
        raise RenewalRejected("Período não contíguo ou já encerrado.")
    return end
