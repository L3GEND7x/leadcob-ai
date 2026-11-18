"""Read-only tenant assistant foundation. No provider calls or shared CRM access."""
from sqlalchemy import select, func
from app.core.account_access import authorize
from app.db.models import WorkspaceLead, WorkspaceTask, WorkspacePortfolio, WorkspaceContact, WorkspaceSuppression
from app.services.commercial_entitlements import check_subscription


def context(db, token, organization_id):
    principal = authorize(db, token, organization_id, "read")
    scope = principal.organization_id
    check_subscription(db, scope)
    stages = dict(db.execute(select(WorkspaceLead.stage, func.count(WorkspaceLead.id))
        .where(WorkspaceLead.organization_id == scope).group_by(WorkspaceLead.stage)).all())
    pending = db.scalar(select(func.count(WorkspaceTask.id)).where(
        WorkspaceTask.organization_id == scope, WorkspaceTask.completed_at.is_(None))) or 0
    portfolios = db.scalar(select(func.count(WorkspacePortfolio.id)).where(
        WorkspacePortfolio.organization_id == scope)) or 0
    suppressed = select(WorkspaceSuppression.cnpj).where(WorkspaceSuppression.organization_id == scope)
    channels = dict(db.execute(select(WorkspaceContact.kind, func.count(func.distinct(WorkspaceContact.cnpj)))
        .where(WorkspaceContact.organization_id == scope, ~WorkspaceContact.cnpj.in_(suppressed))
        .group_by(WorkspaceContact.kind)).all())
    return {
        "organization_id": scope,
        "lead_count": sum(stages.values()),
        "lead_stages": stages,
        "pending_tasks": pending,
        "portfolio_count": portfolios,
        "companies_by_channel": channels,
        "generation_enabled": False,
        "note": "Resumo determinístico da sua organização. Não é uma resposta de IA; geração e histórico privado ainda não habilitados."
    }
