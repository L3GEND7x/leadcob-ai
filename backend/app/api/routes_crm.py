"""v0.5 — Central de comando, inteligência do dia, busca nacional e CRM de prospecção."""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.db.database import get_db
from app.db.models import Company, Interaction, MarketSnapshot, Opportunity, Setting, Suppression, Task
from app.services.cnpj import clean_cnpj, format_cnpj, is_valid_cnpj
from app.services.crm import (CHANNELS, CLOSED, CONTACTED, INTERACTION_KINDS, MANAUS, NOT_APPROACHED, OUTREACH_KINDS,
                              STAGE_LABEL, STAGES, as_utc, audit, blocked_reason, change_stage, get_settings,
                              last_outreach, log_interaction, stage_of, suppression_for)
from app.services.crm import now as crm_now
from app.services.lead_score import score_company, signal_strength
from app.services.segments import SEGMENTS, debt_types_for, profile_for

router = APIRouter(prefix="/api")

REGIONS = {
    "Norte": ["AC", "AM", "AP", "PA", "RO", "RR", "TO"],
    "Nordeste": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
    "Centro-Oeste": ["DF", "GO", "MS", "MT"],
    "Sudeste": ["ES", "MG", "RJ", "SP"],
    "Sul": ["PR", "RS", "SC"],
}
UF_REGION = {uf: r for r, ufs in REGIONS.items() for uf in ufs}
STAGE_ORDER = {k: i for i, (k, _) in enumerate(STAGES)}
KIND_TO_STAGE = {"contato": "primeiro_contato", "follow_up": "aguardando_resposta", "resposta": "em_negociacao",
                 "reuniao": "reuniao_agendada", "proposta": "proposta_enviada", "contrato": "cliente_conquistado"}
CANDIDATE_LIMIT = 3000   # empresas avaliadas por vez para ordenar por pontuação


def iso(v):
    return v.isoformat() if v else None


def today_start_utc() -> datetime:
    now_m = datetime.now(MANAUS)
    return now_m.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def years_active(c) -> float | None:
    try:
        d = date.fromisoformat(c.opened_at)
    except (TypeError, ValueError):
        return None
    return round((date.today() - d).days / 365.25, 1)


def _with_relations(q):
    return q.options(selectinload(Company.opportunities), selectinload(Company.interactions), selectinload(Company.tasks))


def _suppressed_ids(db) -> tuple[set, set]:
    rows = db.query(Suppression.cnpj, Suppression.company_id).all()
    return {r[0] for r in rows if r[0]}, {r[1] for r in rows if r[1]}


def summarize(c, settings, sup) -> dict:
    sup_cnpj, sup_ids = sup
    suppressed = (c.cnpj in sup_cnpj) or (c.id in sup_ids)
    sc = score_company(c, settings, suppressed)
    signals = [o for o in c.opportunities if o.status != "discarded"]
    profile = c.target_profile or (profile_for(c.cnae_main) if c.cnae_main else None)
    last_sig = max((as_utc(o.collected_at) for o in signals), default=None)
    return {
        "id": c.id, "name": c.name, "trade_name": c.trade_name, "cnpj": c.cnpj,
        "cnpj_formatted": format_cnpj(c.cnpj) if c.cnpj and len(c.cnpj) == 14 else c.cnpj,
        "cnae_main": c.cnae_main, "cnae_desc": c.cnae_desc, "segment": c.segment,
        "profile": profile, "profile_label": SEGMENTS.get(profile or "", {}).get("label"),
        "debt_types": [d["label"] for d in debt_types_for(profile)],
        "city": c.city, "state": c.state, "region": UF_REGION.get((c.state or "").upper()),
        "company_size": c.company_size, "capital_social": c.capital_social, "registration_status": c.registration_status,
        "opened_at": c.opened_at, "years_active": years_active(c), "website": c.website,
        "institutional_email": c.institutional_email,
        "stage": stage_of(c), "stage_label": STAGE_LABEL[stage_of(c)], "next_action": c.next_action,
        "next_action_at": iso(c.next_action_at), "potential_value": c.potential_value, "lost_reason": c.lost_reason,
        "score": sc["score"], "band": sc["band"], "band_label": sc["band_label"],
        "signals": len(signals), "last_signal_at": iso(last_sig), "suppressed": suppressed,
        "registry_source": c.registry_source,
    }


# ------------------------------------------------------------- busca nacional
@router.get("/companies/search")
def search_companies(q: str | None = None, uf: str | None = None, region: str | None = None, municipio: str | None = None,
                     cnae: str | None = None, cnae_secundario: bool = True, profile: str | None = None,
                     debt_type: str | None = None, size: str | None = None, situacao: str | None = None,
                     capital_min: float | None = None, capital_max: float | None = None,
                     years_min: float | None = None, years_max: float | None = None,
                     stage: str | None = None, band: str | None = None, has_signal: bool | None = None,
                     include_competitors: bool = False, include_suppressed: bool = False,
                     sort: str = Query(default="score", pattern="^(score|capital|name|opened|recent)$"),
                     page: int = Query(default=1, ge=1), per_page: int = Query(default=25, ge=1, le=100),
                     db: Session = Depends(get_db)):
    """Busca de empresas em todo o Brasil. Filtros por SQL; pontuação calculada sobre o resultado filtrado."""
    query = db.query(Company)
    if q:
        digits = clean_cnpj(q)
        cond = Company.name.ilike(f"%{q}%") | Company.trade_name.ilike(f"%{q}%")
        if len(digits) >= 8:
            cond = cond | Company.cnpj.like(f"{digits}%")
        query = query.filter(cond)
    ufs = [u.strip().upper() for u in (uf or "").split(",") if u.strip()]
    if region:
        if region not in REGIONS:
            raise HTTPException(400, f"Região inválida. Use: {', '.join(REGIONS)}")
        ufs = [u for u in REGIONS[region] if not ufs or u in ufs] or REGIONS[region]
    if ufs:
        query = query.filter(Company.state.in_(ufs))
    if municipio:
        query = query.filter(Company.city.ilike(f"%{municipio}%"))
    if cnae:
        code = re.sub(r"\D", "", cnae)
        cond = Company.cnae_main.like(code + "%")
        if cnae_secundario:
            cond = cond | Company.cnae_secondary.like(f"%{code}%")
        query = query.filter(cond)
    if profile:
        query = query.filter(Company.target_profile == profile)
    if debt_type:
        profiles = [k for k, s in SEGMENTS.items() if debt_type in s.get("debt_types", [])]
        query = query.filter(Company.target_profile.in_(profiles or ["__nenhum__"]))
    if size:
        query = query.filter(Company.company_size == size.upper())
    if situacao:
        query = query.filter(Company.registration_status == situacao.upper())
    if capital_min is not None:
        query = query.filter(Company.capital_social >= capital_min)
    if capital_max is not None:
        query = query.filter(Company.capital_social <= capital_max)
    today = date.today()
    if years_min is not None:
        query = query.filter(Company.opened_at <= (today - timedelta(days=int(years_min * 365.25))).isoformat())
    if years_max is not None:
        query = query.filter(Company.opened_at >= (today - timedelta(days=int(years_max * 365.25))).isoformat())
    if stage:
        if stage not in STAGE_LABEL:
            raise HTTPException(400, "Etapa inválida.")
        query = query.filter(Company.pipeline_stage == stage) if stage != "identificada" else \
            query.filter(or_(Company.pipeline_stage.is_(None), Company.pipeline_stage == "identificada"))
    if not include_competitors:
        query = query.filter(or_(Company.cnae_main.is_(None), ~Company.cnae_main.like("8291%")))
    if has_signal is not None:
        sub = db.query(Opportunity.company_id).filter(Opportunity.status != "discarded")
        query = query.filter(Company.id.in_(sub) if has_signal else ~Company.id.in_(sub))

    settings, sup = get_settings(db), _suppressed_ids(db)
    total = query.count()
    if sort in ("score", "recent") or band:
        rows = _with_relations(query.order_by(Company.capital_social.desc().nullslast(), Company.id)).limit(CANDIDATE_LIMIT).all()
        items = [summarize(c, settings, sup) for c in rows]
        if not include_suppressed:
            items = [i for i in items if not i["suppressed"]]
        if band:
            items = [i for i in items if i["band"] == band]
        key = (lambda i: (i["score"], i["capital_social"] or 0)) if sort == "score" else (lambda i: i["last_signal_at"] or "")
        items.sort(key=key, reverse=True)
        total_scored = len(items)
        page_items = items[(page - 1) * per_page: page * per_page]
        note = (f"Pontuação calculada sobre as {CANDIDATE_LIMIT} primeiras empresas do filtro (por capital social); "
                "refine os filtros para ver o restante.") if total > CANDIDATE_LIMIT else None
        return {"items": page_items, "total": total_scored if (band or not include_suppressed) else total,
                "page": page, "per_page": per_page, "note": note}
    order = {"capital": Company.capital_social.desc().nullslast(), "name": Company.name.asc(),
             "opened": Company.opened_at.asc().nullslast()}[sort]
    rows = _with_relations(query.order_by(order, Company.id)).offset((page - 1) * per_page).limit(per_page).all()
    items = [summarize(c, settings, sup) for c in rows]
    if not include_suppressed:
        items = [i for i in items if not i["suppressed"]]
    return {"items": items, "total": total, "page": page, "per_page": per_page, "note": None}


@router.get("/regions")
def regions():
    return REGIONS


# ------------------------------------------------------------- ficha da empresa
def _company_or_404(db, company_id: int) -> Company:
    c = _with_relations(db.query(Company)).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(404, "Empresa não encontrada.")
    return c


def _signal_view(o) -> dict:
    strength, why = signal_strength(o)
    kind_label = {"public_procurement": "Edital/contratação pública", "hiring": "Vaga de cobrança",
                  "outsourcing": "Possível terceirização"}.get(o.kind, o.kind)
    return {"id": o.id, "type": o.kind, "type_label": kind_label, "title": o.title, "source": o.source_name,
            "url": o.source_url, "captured_at": iso(as_utc(o.collected_at)), "deadline": iso(o.deadline),
            "excerpt": (o.evidence or "")[:600], "confidence": o.confidence, "strength": strength, "reading": why,
            "commercial_signal": o.commercial_signal, "status": o.status,
            "nature": "fato (fonte registrada)" if o.source_url else "indício (sem URL de origem)",
            "caveat": {"public_procurement": "Edital público não é oportunidade privada: a contratação segue a lei de licitações.",
                       "hiring": "Vaga de cobrança não comprova interesse em terceirizar."}.get(o.kind,
                      "Sinal informado manualmente: confirme com a empresa.")}


@router.get("/companies/{company_id}")
def company_sheet(company_id: int, db: Session = Depends(get_db)):
    c = _company_or_404(db, company_id)
    settings, sup = get_settings(db), _suppressed_ids(db)
    summary = summarize(c, settings, sup)
    sc = score_company(c, settings, summary["suppressed"])
    snap = None
    if c.state:
        m = (db.query(MarketSnapshot).filter_by(source="datajud", uf=c.state.upper())
             .order_by(MarketSnapshot.created_at.desc()).first())
        if m:
            snap = {"uf": m.uf, "periodo": m.payload.get("periodo"), "total_processos": m.payload.get("total_processos"),
                    "tipos": m.payload.get("tipos_de_inadimplencia", [])[:5],
                    "aviso": "Contexto regional agregado da Justiça Estadual: não diz nada sobre esta empresa."}
    lo = last_outreach(c)
    return {
        **summary,
        "legal_nature": c.legal_nature, "cnae_secondary": (c.cnae_secondary or "").split(",") if c.cnae_secondary else [],
        "notes": c.notes, "registry_updated_at": iso(c.registry_updated_at), "created_at": iso(as_utc(c.created_at)),
        "score_detail": sc,
        "signals_detail": [_signal_view(o) for o in sorted(c.opportunities, key=lambda o: as_utc(o.collected_at) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)],
        "timeline": [{"id": i.id, "kind": i.kind, "kind_label": INTERACTION_KINDS.get(i.kind, i.kind), "channel": i.channel,
                      "summary": i.summary, "outcome": i.outcome, "at": iso(as_utc(i.happened_at))}
                     for i in sorted(c.interactions, key=lambda i: as_utc(i.happened_at), reverse=True)],
        "tasks": [{"id": t.id, "title": t.title, "kind": t.kind, "due_at": iso(as_utc(t.due_at)), "done": t.done}
                  for t in c.tasks],
        "blocked_reason": blocked_reason(db, c),
        "last_outreach_at": iso(lo),
        "market_context": snap,
        "stages": [{"key": k, "label": v} for k, v in STAGES],
    }


class CompanyPatch(BaseModel):
    stage: str | None = None
    stage_reason: str | None = Field(default=None, max_length=500)
    next_action: str | None = Field(default=None, max_length=500)
    next_action_at: datetime | None = None
    potential_value: float | None = Field(default=None, ge=0)
    lost_reason: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=5000)
    website: str | None = Field(default=None, max_length=500)
    institutional_email: str | None = Field(default=None, max_length=255)


@router.patch("/companies/{company_id}")
def update_company(company_id: int, payload: CompanyPatch, db: Session = Depends(get_db)):
    c = _company_or_404(db, company_id)
    data = payload.model_dump(exclude_unset=True)
    if "stage" in data:
        new = data["stage"]
        if new not in STAGE_LABEL:
            raise HTTPException(400, "Etapa inválida.")
        if new == "perdido" and not (data.get("lost_reason") or c.lost_reason):
            raise HTTPException(400, "Informe o motivo da perda para marcar como 'Perdido'.")
        if new != "nao_contatar" and suppression_for(db, c):
            raise HTTPException(409, "Empresa na lista de supressão: remova-a da lista (Configurações) antes de mudar a etapa.")
    if "lost_reason" in data:
        c.lost_reason = data["lost_reason"]
    if "stage" in data:
        change_stage(db, c, data["stage"], data.get("stage_reason") or (data.get("lost_reason") if data["stage"] == "perdido" else None))
    changed = {}
    for field in ("next_action", "next_action_at", "potential_value", "notes", "website", "institutional_email"):
        if field in data and getattr(c, field) != data[field]:
            changed[field] = {"from": str(getattr(c, field)) if getattr(c, field) is not None else None,
                              "to": str(data[field]) if data[field] is not None else None}
            setattr(c, field, data[field])
    if "potential_value" in changed:
        log_interaction(db, c, "nota", f"Potencial comercial informado: R$ {data['potential_value']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        if data["potential_value"] is not None else "Potencial comercial removido")
    if "next_action" in changed or "next_action_at" in changed:
        when = f" em {as_utc(c.next_action_at).astimezone(MANAUS):%d/%m/%Y %H:%M}" if c.next_action_at else ""
        log_interaction(db, c, "nota", f"Próxima atividade: {c.next_action or '—'}{when}")
    if changed:
        audit(db, "company_updated", "company", c.id, changed)
    db.commit()
    return company_sheet(company_id, db)


class CompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=220)
    cnpj: str | None = None
    state: str | None = Field(default=None, max_length=2)
    city: str | None = Field(default=None, max_length=100)
    segment: str | None = Field(default=None, max_length=120)
    cnae_main: str | None = Field(default=None, max_length=7)
    website: str | None = Field(default=None, max_length=500)
    institutional_email: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=5000)


@router.post("/companies", status_code=201)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db)):
    cnpj = clean_cnpj(payload.cnpj) if payload.cnpj else None
    if cnpj:
        if not is_valid_cnpj(cnpj):
            raise HTTPException(400, "CNPJ inválido.")
        existing = db.query(Company).filter_by(cnpj=cnpj).first()
        if existing:
            raise HTTPException(409, f"Empresa já cadastrada (id {existing.id}): {existing.name}.")
    else:
        existing = db.query(Company).filter(func.lower(Company.name) == payload.name.strip().lower()).first()
        if existing:
            raise HTTPException(409, f"Empresa já cadastrada (id {existing.id}): {existing.name}. Informe o CNPJ para diferenciar.")
    c = Company(name=payload.name, cnpj=cnpj, state=(payload.state or "").upper() or None, city=payload.city,
                segment=payload.segment, cnae_main=payload.cnae_main, website=payload.website,
                institutional_email=payload.institutional_email, notes=payload.notes, pipeline_stage="identificada",
                target_profile=profile_for(payload.cnae_main) if payload.cnae_main else None,
                registry_source="Cadastro manual", created_at=crm_now())
    db.add(c); db.flush()
    log_interaction(db, c, "sistema", "Empresa cadastrada manualmente")
    audit(db, "company_created", "company", c.id, {"source": "manual"})
    db.commit()
    return company_sheet(c.id, db)


# ------------------------------------------------------------- interações e tarefas
class InteractionIn(BaseModel):
    kind: str
    channel: str | None = None
    summary: str = Field(min_length=2, max_length=5000)
    outcome: str | None = Field(default=None, max_length=30)
    happened_at: datetime | None = None
    confirm_repeat: bool = False
    follow_up_days: int | None = Field(default=None, ge=1, le=90)


@router.post("/companies/{company_id}/interactions", status_code=201)
def add_interaction(company_id: int, payload: InteractionIn, db: Session = Depends(get_db)):
    c = _company_or_404(db, company_id)
    if payload.kind not in INTERACTION_KINDS or payload.kind in ("etapa", "sistema"):
        raise HTTPException(400, f"Tipo inválido. Use: {', '.join(k for k in INTERACTION_KINDS if k not in ('etapa', 'sistema'))}")
    if payload.channel and payload.channel not in CHANNELS:
        raise HTTPException(400, f"Canal inválido. Use: {', '.join(sorted(CHANNELS))}")
    if payload.kind in OUTREACH_KINDS:
        if reason := blocked_reason(db, c):
            raise HTTPException(409, reason)
        settings = get_settings(db)
        lo = last_outreach(c)
        gap = int(settings.get("dias_entre_contatos") or 7)
        if lo and not payload.confirm_repeat and datetime.now(timezone.utc) - lo < timedelta(days=gap):
            raise HTTPException(409, f"Último contato em {lo.astimezone(MANAUS):%d/%m/%Y}, há menos de {gap} dias. "
                                     "Confirme para registrar outro contato (evita abordagens repetidas).")
    it = log_interaction(db, c, payload.kind, payload.summary, payload.channel, payload.outcome, payload.happened_at)
    target = KIND_TO_STAGE.get(payload.kind)
    current = stage_of(c)
    if (target and current not in ("perdido", "nao_contatar") and not suppression_for(db, c)
            and STAGE_ORDER[target] > STAGE_ORDER.get(current, 0)):
        change_stage(db, c, target, f"registro de {INTERACTION_KINDS[payload.kind].lower()}")
    if payload.follow_up_days:
        db.add(Task(company_id=c.id, title=f"Follow-up: {c.name}"[:250], kind="follow_up",
                    due_at=(as_utc(payload.happened_at) or crm_now()) + timedelta(days=payload.follow_up_days)))
    audit(db, "interaction_added", "company", c.id, {"kind": payload.kind, "channel": payload.channel})
    db.commit()
    return {"id": it.id, "stage": stage_of(c), "stage_label": STAGE_LABEL[stage_of(c)]}


class TaskIn(BaseModel):
    title: str = Field(min_length=2, max_length=250)
    kind: str = Field(default="follow_up", max_length=30)
    due_at: datetime | None = None


@router.post("/companies/{company_id}/tasks", status_code=201)
def add_task(company_id: int, payload: TaskIn, db: Session = Depends(get_db)):
    c = _company_or_404(db, company_id)
    t = Task(company_id=c.id, title=payload.title, kind=payload.kind, due_at=payload.due_at, created_at=crm_now())
    db.add(t); db.flush()
    audit(db, "task_created", "task", t.id, {"company_id": c.id, "title": t.title})
    db.commit()
    return {"id": t.id}


class TaskPatch(BaseModel):
    done: bool | None = None
    due_at: datetime | None = None
    title: str | None = Field(default=None, max_length=250)


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, payload: TaskPatch, db: Session = Depends(get_db)):
    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "Tarefa não encontrada.")
    data = payload.model_dump(exclude_unset=True)
    if "done" in data:
        t.done = data["done"]; t.done_at = crm_now() if data["done"] else None
        if data["done"] and t.company_id:
            c = db.get(Company, t.company_id)
            log_interaction(db, c, "nota", f"Tarefa concluída: {t.title}")
    for f in ("due_at", "title"):
        if f in data:
            setattr(t, f, data[f])
    audit(db, "task_updated", "task", t.id, {k: str(v) for k, v in data.items()})
    db.commit()
    return {"id": t.id, "done": t.done}


def _task_view(t, now) -> dict:
    due = as_utc(t.due_at)
    return {"id": t.id, "title": t.title, "kind": t.kind, "due_at": iso(due), "done": t.done,
            "overdue": bool(due and not t.done and due < now), "company_id": t.company_id,
            "company_name": t.company.name if t.company else None}


@router.get("/tasks")
def list_tasks(status: str = Query(default="open", pattern="^(open|overdue|done|all)$"), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    q = db.query(Task).options(selectinload(Task.company))
    if status in ("open", "overdue"):
        q = q.filter(Task.done.is_(False))
    elif status == "done":
        q = q.filter(Task.done.is_(True))
    items = [_task_view(t, now) for t in q.order_by(Task.due_at.asc().nullslast()).limit(500).all()]
    return [i for i in items if i["overdue"]] if status == "overdue" else items


# ------------------------------------------------------------- supressão e configurações
class SuppressionIn(BaseModel):
    company_id: int | None = None
    cnpj: str | None = None
    reason: str = Field(default="", max_length=1000)


@router.get("/suppression")
def list_suppression(db: Session = Depends(get_db)):
    return [{"id": s.id, "cnpj": s.cnpj, "company_id": s.company_id, "company_name": s.company_name, "reason": s.reason,
             "created_at": iso(as_utc(s.created_at))} for s in db.query(Suppression).order_by(Suppression.created_at.desc())]


@router.post("/suppression", status_code=201)
def add_suppression(payload: SuppressionIn, db: Session = Depends(get_db)):
    c = db.get(Company, payload.company_id) if payload.company_id else None
    cnpj = clean_cnpj(payload.cnpj) if payload.cnpj else (c.cnpj if c else None)
    if not c and not cnpj:
        raise HTTPException(400, "Informe a empresa ou o CNPJ.")
    if c is None and cnpj:
        c = db.query(Company).filter_by(cnpj=cnpj).first()
    if c and suppression_for(db, c):
        raise HTTPException(409, "Empresa já está na lista de supressão.")
    s = Suppression(cnpj=cnpj, company_id=c.id if c else None, company_name=c.name if c else None, reason=payload.reason,
                    created_at=crm_now())
    db.add(s)
    if c:
        if stage_of(c) != "nao_contatar":
            c.pipeline_stage, c.stage_updated_at = "nao_contatar", crm_now()
        log_interaction(db, c, "sistema", "Incluída na lista de supressão" + (f": {payload.reason}" if payload.reason else ""))
    audit(db, "suppression_added", "suppression", None, {"cnpj": cnpj, "company_id": c.id if c else None, "reason": payload.reason})
    db.commit()
    return {"id": s.id}


@router.delete("/suppression/{sup_id}")
def remove_suppression(sup_id: int, db: Session = Depends(get_db)):
    s = db.get(Suppression, sup_id)
    if not s:
        raise HTTPException(404, "Registro não encontrado.")
    audit(db, "suppression_removed", "suppression", sup_id, {"cnpj": s.cnpj, "company_id": s.company_id})
    if s.company_id and (c := db.get(Company, s.company_id)):
        log_interaction(db, c, "sistema", "Removida da lista de supressão")
        if stage_of(c) == "nao_contatar":
            c.pipeline_stage, c.stage_updated_at = "acompanhar_futuramente", crm_now()
    db.delete(s); db.commit()
    return {"ok": True}


class SettingsIn(BaseModel):
    ufs_atuacao: list[str] | None = None
    dias_entre_contatos: int | None = Field(default=None, ge=1, le=90)
    servico: str | None = Field(default=None, max_length=200)
    remetente_nome: str | None = Field(default=None, max_length=120)
    remetente_empresa: str | None = Field(default=None, max_length=160)
    remetente_contato: str | None = Field(default=None, max_length=200)


@router.get("/settings")
def read_settings(db: Session = Depends(get_db)):
    return get_settings(db)


@router.put("/settings")
def write_settings(payload: SettingsIn, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    if "ufs_atuacao" in data:
        ufs = [u.strip().upper() for u in data["ufs_atuacao"] if u.strip()]
        bad = [u for u in ufs if u not in UF_REGION]
        if bad:
            raise HTTPException(400, f"UF inválida: {', '.join(bad)}")
        data["ufs_atuacao"] = sorted(set(ufs))
    row = db.get(Setting, "geral")
    value = {**get_settings(db), **data}
    if row:
        row.value = value; row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(Setting(key="geral", value=value))
    audit(db, "settings_updated", "settings", None, data)
    db.commit()
    return value


# ------------------------------------------------------------- central de comando
def _pipeline_candidates(db):
    """Empresas que importam para o trabalho do dia: com sinal, no funil ou com mais capital."""
    with_signal = db.query(Opportunity.company_id).filter(Opportunity.status != "discarded")
    q = _with_relations(db.query(Company)).filter(
        or_(Company.id.in_(with_signal), Company.pipeline_stage.isnot(None), Company.next_action_at.isnot(None)))
    rows = q.limit(CANDIDATE_LIMIT).all()
    if len(rows) < CANDIDATE_LIMIT:
        seen = {c.id for c in rows}
        extra = (_with_relations(db.query(Company)).filter(Company.target_profile.isnot(None))
                 .order_by(Company.capital_social.desc().nullslast()).limit(CANDIDATE_LIMIT - len(rows)).all())
        rows += [c for c in extra if c.id not in seen]
    return rows


@router.get("/command-center")
def command_center(db: Session = Depends(get_db)):
    settings, sup = get_settings(db), _suppressed_ids(db)
    now, today = datetime.now(timezone.utc), today_start_utc()
    stage_counts = dict(db.query(func.coalesce(Company.pipeline_stage, "identificada"), func.count()).group_by(
        func.coalesce(Company.pipeline_stage, "identificada")).all())

    def companies_with(kinds):
        return db.query(func.count(func.distinct(Interaction.company_id))).filter(Interaction.kind.in_(kinds)).scalar() or 0

    contacted = companies_with(list(OUTREACH_KINDS))
    contracts = stage_counts.get("cliente_conquistado", 0)
    potential = db.query(func.sum(Company.potential_value)).filter(
        or_(Company.pipeline_stage.is_(None), ~Company.pipeline_stage.in_(["perdido", "nao_contatar"]))).scalar()
    kpis = {
        "empresas_total": db.query(Company).count(),
        "empresas_novas_hoje": db.query(Company).filter(Company.created_at >= today).count(),
        "oportunidades_novas_hoje": db.query(Opportunity).filter(Opportunity.collected_at >= today,
                                                                 Opportunity.status != "discarded").count(),
        "leads_qualificados": sum(v for k, v in stage_counts.items() if k not in ("identificada", "em_pesquisa", "perdido", "nao_contatar", "acompanhar_futuramente")),
        "leads_nao_abordados": stage_counts.get("qualificada", 0) + stage_counts.get("pronta_abordagem", 0),
        "contatos_realizados": contacted,
        "respostas": companies_with(["resposta"]),
        "reunioes": max(companies_with(["reuniao"]), stage_counts.get("reuniao_agendada", 0)),
        "propostas": max(companies_with(["proposta"]), stage_counts.get("proposta_enviada", 0)),
        "contratos": contracts,
        "taxa_conversao": round(100 * contracts / contacted, 1) if contacted else None,
        "valor_potencial": potential,
        "notas": {"valor_potencial": "Soma dos valores informados por você nas fichas (não é estimativa do sistema).",
                  "taxa_conversao": "Contratos ÷ empresas contatadas."},
    }
    cands = _pipeline_candidates(db)
    scored = [(c, summarize(c, settings, sup)) for c in cands]
    open_ = [(c, s) for c, s in scored if s["stage"] not in CLOSED and not s["suppressed"] and s["band"] not in ("concorrente", "inativa")]
    need_approach = sorted([s for c, s in open_ if s["stage"] in ("qualificada", "pronta_abordagem")], key=lambda s: -s["score"])[:10]
    top = sorted([s for c, s in open_], key=lambda s: -s["score"])[:10]
    week = now - timedelta(days=7)
    new_signals = sorted([s for c, s in open_ if s["last_signal_at"] and datetime.fromisoformat(s["last_signal_at"]) >= week],
                         key=lambda s: s["last_signal_at"], reverse=True)[:10]
    overdue_co = [{"company_id": c.id, "company_name": c.name, "title": c.next_action or "Próxima atividade",
                   "due_at": iso(as_utc(c.next_action_at)), "kind": "proxima_atividade"}
                  for c, s in scored if c.next_action_at and as_utc(c.next_action_at) < now and s["stage"] not in CLOSED]
    tasks_open = [_task_view(t, now) for t in db.query(Task).options(selectinload(Task.company)).filter(Task.done.is_(False))
                  .order_by(Task.due_at.asc().nullslast()).limit(200).all()]
    overdue = sorted([{"company_id": t["company_id"], "company_name": t["company_name"], "title": t["title"],
                       "due_at": t["due_at"], "kind": "tarefa", "task_id": t["id"]} for t in tasks_open if t["overdue"]] + overdue_co,
                     key=lambda x: x["due_at"] or "")
    recent = (db.query(Opportunity).options(selectinload(Opportunity.company)).filter(Opportunity.status != "discarded")
              .order_by(Opportunity.collected_at.desc()).limit(10).all())
    return {
        "kpis": kpis,
        "pipeline": [{"key": k, "label": v, "count": stage_counts.get(k, 0)} for k, v in STAGES],
        "precisam_abordagem": need_approach,
        "followups_atrasados": overdue[:15],
        "oportunidades_recentes": [{"id": o.id, "company_id": o.company_id, "company_name": o.company.name, "title": o.title,
                                    "kind": o.kind, "source": o.source_name, "url": o.source_url,
                                    "captured_at": iso(as_utc(o.collected_at)), "commercial_signal": o.commercial_signal} for o in recent],
        "maior_pontuacao": top,
        "novos_sinais": new_signals,
        "tarefas_pendentes": [t for t in tasks_open if not t["overdue"]][:15],
        "base_avaliada": len(cands),
    }


@router.get("/pipeline")
def pipeline(db: Session = Depends(get_db)):
    """Funil do CRM: empresas que já saíram de 'Empresa identificada', agrupadas por etapa."""
    settings, sup = get_settings(db), _suppressed_ids(db)
    rows = (_with_relations(db.query(Company)).filter(Company.pipeline_stage.isnot(None), Company.pipeline_stage != "identificada")
            .order_by(Company.stage_updated_at.desc().nullslast()).limit(CANDIDATE_LIMIT).all())
    groups = {k: [] for k, _ in STAGES}
    for c in rows:
        s = summarize(c, settings, sup)
        s["stage_updated_at"] = iso(as_utc(c.stage_updated_at))
        groups[s["stage"]].append(s)
    identified = db.query(Company).filter(or_(Company.pipeline_stage.is_(None), Company.pipeline_stage == "identificada")).count()
    return {"stages": [{"key": k, "label": v, "count": identified if k == "identificada" else len(groups[k]),
                        "items": [] if k == "identificada" else groups[k]} for k, v in STAGES]}


# ------------------------------------------------------------- inteligência do dia
def _service_and_hook(c, s, best) -> dict:
    sector = s["profile_label"] or "seu setor"
    debt = ", ".join(s["debt_types"][:2]).lower() or "contas a receber"
    if best is not None and best.kind == "public_procurement" and best.opportunity_class == "edital_aberto":
        return {"servico": "Participação no edital/credenciamento publicado (cobrança/recuperação de crédito).",
                "servico_natureza": "fato (edital publicado)",
                "abertura": f"Proposta formal no próprio processo: ler o edital em {best.source_url} e verificar habilitação, "
                            "remuneração e prazo. Em licitação, o contato segue as regras do edital.",
                "proxima_acao": "Baixar e ler o edital; montar checklist de habilitação até o prazo de propostas."}
    if best is not None and best.kind == "hiring":
        role = best.title
        if best.opportunity_class == "operacao_interna":
            serv = "Reforço ou terceirização de faixas da cobrança (complementar a equipe em formação)."
            hook = (f"Vi que vocês estão contratando para '{role}'. Empresas que estruturam a cobrança costumam combinar "
                    "equipe interna com um parceiro para faixas de atraso específicas; posso mostrar como funcionaria.")
        else:
            serv = "Credenciamento como assessoria parceira de cobrança/recuperação."
            hook = (f"Vi a vaga '{role}', que indica uma área de recuperação de crédito estruturada. Áreas assim "
                    "costumam trabalhar com assessorias credenciadas; gostaria de saber como funciona o credenciamento de vocês.")
        return {"servico": serv, "servico_natureza": "hipótese baseada em fato (vaga publicada)", "abertura": hook,
                "proxima_acao": "Identificar a área de crédito/cobrança (site ou página de carreira) e enviar a primeira mensagem."}
    return {"servico": f"Diagnóstico e cobrança de {debt}.",
            "servico_natureza": "hipótese (setor costuma ter este tipo de recebível)",
            "abertura": (f"Trabalhamos com cobrança e recuperação de crédito para empresas de {sector.lower()}. "
                         "Gostaria de entender como vocês organizam hoje o acompanhamento das contas a receber."),
            "proxima_acao": "Pesquisar o site institucional e o contato do financeiro antes da abordagem."}


@router.get("/daily-intelligence")
def daily_intelligence(limit: int = Query(default=5, ge=1, le=20), db: Session = Depends(get_db)):
    settings, sup = get_settings(db), _suppressed_ids(db)
    gap = timedelta(days=int(settings.get("dias_entre_contatos") or 7))
    now = datetime.now(timezone.utc)
    picks = []
    for c in _pipeline_candidates(db):
        s = summarize(c, settings, sup)
        if s["stage"] in CLOSED or s["stage"] == "acompanhar_futuramente" or s["suppressed"] or s["band"] in ("concorrente", "inativa"):
            continue
        lo = last_outreach(c)
        if lo and now - lo < gap:
            continue
        picks.append((s["score"], c, s))
    picks.sort(key=lambda x: -x[0])
    out = []
    for score, c, s in picks[:limit]:
        sc = score_company(c, settings, False)
        signals = [o for o in c.opportunities if o.status != "discarded"]
        best = max(signals, key=lambda o: (signal_strength(o)[0], as_utc(o.collected_at) or datetime.min.replace(tzinfo=timezone.utc))) if signals else None
        reasons = sorted([p for p in sc["components"] if p["points"] > 0], key=lambda p: -p["points"])[:3]
        fatos = [f"{p['label']}: {p['reason']}" for p in sc["components"] if p["nature"] == "fato" and p["points"] > 0]
        indicios = [f"{p['label']}: {p['reason']}" for p in sc["components"] if p["nature"] == "indício" and p["points"] > 0]
        hipoteses = [f"{p['label']}: {p['reason']}" for p in sc["components"] if p["nature"] == "hipótese" and p["points"] > 0]
        channel = ("e-mail institucional cadastrado" if c.institutional_email else "site institucional" if c.website
                   else "nenhum canal cadastrado: localizar no site da empresa ou no edital/vaga")
        out.append({
            **s,
            "motivo": "; ".join(f"{p['reason']} (+{p['points']})" for p in reasons),
            "evidencia": ({"titulo": best.title, "fonte": best.source_name, "url": best.source_url,
                           "captada_em": iso(as_utc(best.collected_at)), "natureza": "fato"} if best else
                          {"titulo": "Sem sinal de demanda captado: indicação apenas pelo cadastro e pelo setor.", "natureza": "hipótese"}),
            "canal": channel,
            **_service_and_hook(c, s, best),
            "fatos": fatos, "indicios": indicios, "hipoteses": hipoteses,
            "cuidado": "Não afirme que a empresa tem inadimplência: nenhuma fonte pública usada aqui comprova isso.",
        })
    return {"gerado_em": iso(now), "itens": out,
            "metodo": "Regras explicáveis sobre os dados do banco (sem modelo de linguagem). Empresas contatadas há menos de "
                      f"{gap.days} dias, encerradas, na lista de supressão, concorrentes ou inativas ficam de fora."}


# ------------------------------------------------------------- exportação
@router.get("/export/companies.csv")
def export_companies(uf: str | None = None, profile: str | None = None, stage: str | None = None,
                     limit: int = Query(default=2000, ge=1, le=5000), db: Session = Depends(get_db)):
    """Exporta só dados de pessoa jurídica, sem empresas da lista de supressão."""
    q = db.query(Company)
    if uf:
        q = q.filter(Company.state.in_([u.strip().upper() for u in uf.split(",")]))
    if profile:
        q = q.filter(Company.target_profile == profile)
    if stage:
        q = q.filter(Company.pipeline_stage == stage)
    sup_cnpj, sup_ids = _suppressed_ids(db)
    rows = [c for c in q.order_by(Company.name).limit(limit).all() if c.cnpj not in sup_cnpj and c.id not in sup_ids]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["cnpj", "razao_social", "nome_fantasia", "cnae", "descricao_cnae", "perfil", "municipio", "uf", "porte",
                "capital_social", "etapa", "proxima_atividade", "site", "fonte_cadastro"])
    for c in rows:
        w.writerow([format_cnpj(c.cnpj) if c.cnpj else "", c.name, c.trade_name or "", c.cnae_main or "", c.cnae_desc or "",
                    SEGMENTS.get(c.target_profile or "", {}).get("label", ""), c.city or "", c.state or "",
                    c.company_size or "", c.capital_social or "", STAGE_LABEL[stage_of(c)], c.next_action or "",
                    c.website or "", c.registry_source or ""])
    audit(db, "export", "company", None, {"rows": len(rows), "uf": uf, "profile": profile, "stage": stage})
    db.commit()
    return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=leadcob-empresas.csv"})
