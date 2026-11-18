"""Tenant-scoped aggregate context and opt-in, budgeted generation."""
from sqlalchemy import select, func, update
from datetime import datetime, timezone
from math import isfinite, ceil
import json
from fastapi import HTTPException
from app.core.config import settings
from app.db.models import WorkspaceAssistantExchange as Exchange, WorkspaceAssistantBudgetLock as BudgetLock
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
        "generation_enabled": enabled(),
        "note": "Resumo determinístico da sua organização. Não é uma resposta de IA; Geração opcional, com orçamento separado e histórico individual."
    }


def enabled():
    return (settings.workspace_assistant_enabled and bool(settings.openai_api_key.strip())
        and bool(settings.openai_model.strip()) and all(isfinite(x) and 0 < x <= 1000 for x in (
        settings.workspace_assistant_monthly_budget_usd, settings.openai_input_usd_per_million,
        settings.openai_output_usd_per_million)))


def history(db, token, organization_id):
    principal=authorize(db,token,organization_id,"read")
    rows=db.scalars(select(Exchange).where(Exchange.organization_id==organization_id,
        Exchange.user_id==principal.user_id).order_by(Exchange.created_at.desc(),Exchange.id.desc()).limit(50))
    return [dict(id=x.id,prompt=x.prompt,answer=x.answer,status=x.status) for x in rows]


def generate(db, token, organization_id, csrf, request_id, prompt):
    principal=authorize(db,token,organization_id,"write",csrf=csrf)
    if not enabled():
        raise HTTPException(503,"Geração comercial indisponível.")
    plan=check_subscription(db,organization_id)
    # Explicit conservative provisional quotas, not advertised plan entitlements.
    cap_by_price={2700:30,11700:120,39700:400}
    quota=cap_by_price.get(plan.monthly_price_cents,0)
    if not quota:
        raise HTTPException(403,"Plano sem acesso à geração experimental.")
    month=datetime.now(timezone.utc).strftime("%Y-%m")
    # Global serialization across tenant reservations; no lock held during provider call.
    changed=db.execute(update(BudgetLock).where(BudgetLock.id==1).values(id=1))
    if changed.rowcount!=1:
        raise HTTPException(503,"Controle de orçamento indisponível.")
    principal=authorize(db,token,organization_id,"write",csrf=csrf)
    check_subscription(db,organization_id)
    if db.get(Exchange,request_id):
        raise HTTPException(409,"Solicitação já registrada.")
    n=db.scalar(select(func.count()).select_from(Exchange).where(
        Exchange.organization_id==organization_id,Exchange.month==month))
    if n>=quota:
        raise HTTPException(429,"Limite experimental mensal atingido.")
    used=db.scalar(select(func.coalesce(func.sum(Exchange.charged_micro_usd),0)).where(Exchange.month==month))
    snapshot=context(db,token,organization_id)
    payload=json.dumps({"pergunta":prompt,"resumo":{k:snapshot[k] for k in (
        "lead_count","lead_stages","pending_tasks","portfolio_count","companies_by_channel")}},ensure_ascii=False)
    if len(payload.encode())>16000:
        raise HTTPException(422,"Contexto excede o limite.")
    input_price=settings.openai_input_usd_per_million
    output_price=settings.openai_output_usd_per_million
    model=settings.openai_model
    reserved=ceil(20000*input_price+512*output_price)
    if used+reserved>int(settings.workspace_assistant_monthly_budget_usd*1000000):
        raise HTTPException(429,"Orçamento comercial indisponível.")
    row=Exchange(id=request_id,organization_id=organization_id,user_id=principal.user_id,
        month=month,prompt=prompt,answer=None,status="running",reserved_micro_usd=reserved,
        charged_micro_usd=reserved)
    db.add(row)
    db.commit()
    answer=None
    actual=reserved
    status="failed"
    try:
        from openai import OpenAI
        with OpenAI(api_key=settings.openai_api_key,timeout=25,max_retries=0) as client:
            response=client.responses.create(model=model,
                instructions="Assistente B2B em português. Use somente o resumo agregado fornecido. "
                "Não invente empresas, contatos, valores ou ações. Não solicite dados pessoais.",
                input=payload,max_output_tokens=512,store=False)
        if response.status=="completed" and response.output_text.strip():
            answer=response.output_text[:10000]
            actual=ceil(response.usage.input_tokens*input_price+response.usage.output_tokens*output_price)
            status="completed"
    except Exception:
        # Uncertain usage retains reservation; no retry and no provider details.
        pass
    db.execute(update(Exchange).where(Exchange.id==request_id).values(
        answer=answer,status=status,charged_micro_usd=actual))
    db.commit()
    authorize(db,token,organization_id,"read")
    return dict(id=request_id,status=status,answer=answer)
