from datetime import datetime, timezone
from app.core.security import stamp
from app.db.models import CommercialSubscription, CommercialPlan


def subscription_status(row, now=None):
    if row is None:
        return 'unassigned'
    if row.status == 'cancelled':
        return 'cancelled'
    now = now or datetime.now(timezone.utc)
    if now < stamp(row.starts_at):
        return 'scheduled'
    if now >= stamp(row.ends_at):
        return 'expired'
    return 'active'


def describe(db, organization_id, now=None):
    row=db.get(CommercialSubscription,organization_id)
    if row is None:
        return {'organization_id':organization_id,'status':'unassigned','plan':None}
    plan=db.get(CommercialPlan,row.plan_id)
    return dict(organization_id=organization_id,status=subscription_status(row,now),
                starts_at=stamp(row.starts_at),ends_at=stamp(row.ends_at),
                plan=dict(id=plan.id,code=plan.code,name=plan.name,currency='BRL',
                          monthly_price_cents=plan.monthly_price_cents,
                          **{k:getattr(plan,k) for k in ('max_members','max_leads','max_contacts',
                                                       'max_tasks','max_portfolios','max_titles')}))
