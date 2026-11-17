"""Commercial HTTP entitlements. Caller owns transaction."""
from sqlalchemy import select, update, func
from fastapi import HTTPException
from app.core.config import settings
from app.db.models import (Organization, Membership, WorkspaceLead, WorkspaceTask,
    WorkspaceContact, WorkspacePortfolio, WorkspacePortfolioTitle,
    CommercialSubscription, CommercialPlan)
from app.services.commercial_subscriptions import subscription_status

MODELS = {'members':Membership, 'leads':WorkspaceLead, 'tasks':WorkspaceTask,
          'contacts':WorkspaceContact, 'portfolios':WorkspacePortfolio}


def lock_organization(db, organization_id):
    # A no-op UPDATE locks the organization on PostgreSQL and serializes SQLite
    # writers. Hold the lock through checking usage and committing the mutation.
    result = db.execute(update(Organization).where(Organization.id==organization_id)
                        .values(active=Organization.active))
    if result.rowcount != 1:
        raise HTTPException(404, 'Organização não encontrada.')


def usage(db, organization_id):
    result = {key:db.scalar(select(func.count()).select_from(model)
                            .where(model.organization_id==organization_id))
              for key,model in MODELS.items()}
    result['titles'] = db.scalar(select(func.count()).select_from(WorkspacePortfolioTitle)
        .join(WorkspacePortfolio, WorkspacePortfolio.id==WorkspacePortfolioTitle.portfolio_id)
        .where(WorkspacePortfolio.organization_id==organization_id))
    return result


def check_subscription(db, organization_id):
    row=db.get(CommercialSubscription,organization_id)
    if subscription_status(row)!='active':
        raise HTTPException(402, 'Assinatura sem vigência ativa.')
    plan=db.get(CommercialPlan,row.plan_id)
    if plan is None:
        raise HTTPException(402, 'Plano indisponível.')
    # Deactivation prevents new assignments, not already contracted access.
    return plan


def enforce(db, organization_id, resource=None, *, locked=False, require_active=True):
    if not settings.commercial_entitlements_enabled:
        return
    if not locked:
        lock_organization(db,organization_id)
    plan=check_subscription(db,organization_id) if require_active else None
    if resource:
        if plan is None:
            plan=check_subscription(db,organization_id)
        if usage(db,organization_id)[resource]>=getattr(plan,'max_'+resource):
            raise HTTPException(409, 'Limite contratado atingido: '+resource+'.')
