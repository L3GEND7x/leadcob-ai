from datetime import datetime, timezone
from types import SimpleNamespace as Obj
import pytest
from app.services.commercial_renewals import renewal_end, RenewalRejected


def test_only_paid_contiguous_same_plan_renewal():
    now = datetime(2026, 11, 17, tzinfo=timezone.utc)
    sub = Obj(status="active", organization_id=1, plan_id=2,
              ends_at=datetime(2026, 12, 1, tzinfo=timezone.utc))
    invoice = Obj(organization_id=1, plan_id=2, status="paid", amount_cents=2700,
                  payment_reference="bank-proof", paid_at=now,
                  period_start="2026-12-01", period_end="2027-01-01")
    plan = Obj(id=2, active=True)
    assert renewal_end(sub, invoice, plan, now) == datetime(2027, 1, 1, tzinfo=timezone.utc)
    for changes in (dict(status="open"), dict(organization_id=3), dict(plan_id=3),
                    dict(payment_reference=None), dict(period_start="2026-12-02")):
        with pytest.raises(RenewalRejected):
            renewal_end(sub, Obj(**(vars(invoice) | changes)), plan, now)
    with pytest.raises(RenewalRejected):
        renewal_end(Obj(**(vars(sub) | {"status":"cancelled"})), invoice, plan, now)
