import hashlib
import json
import re
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.agents.pipeline import run_pipeline
from app.collectors import cnpj_api, jobboards, pncp
from app.db.database import get_db
from app.db.models import CaptureRun, Company, Opportunity
from app.schemas import OpportunityCreate
from app.services.cnpj import clean_cnpj, format_cnpj
from app.services.procurement import parse_dt, score_procurement
from app.services.jobs import COMPETITOR_CNAE, score_job
from app.services.segments import SEGMENTS, profile_for
from app.services.scoring import score_opportunity

router = APIRouter(prefix="/api")
KINDS = ("hiring", "outsourcing", "public_procurement")


def iso(value):
    return value.isoformat() if value else None


def serialize(o):
    return {
        "id": o.id, "company_id": o.company_id, "company_name": o.company.name, "cnpj": o.company.cnpj,
        "segment": o.company.segment, "city": o.company.city, "state": o.company.state, "kind": o.kind,
        "title": o.title, "source_key": o.source_key, "description": o.description, "evidence": o.evidence,
        "source_name": o.source_name, "source_url": o.source_url, "origin_url": o.origin_url,
        "score": o.score, "score_reason": o.score_reason, "status": o.status, "confidence": o.confidence,
        "is_verified": o.is_verified, "collected_at": iso(o.collected_at),
        "relevance": o.relevance, "relevance_reason": o.relevance_reason,
        "opportunity_class": o.opportunity_class, "evidence_level": o.evidence_level,
        "commercial_signal": o.commercial_signal, "deadline": iso(o.deadline),
        "estimated_value": o.estimated_value, "modality_name": o.modality_name,
        "cnae_main": o.company.cnae_main, "cnae_desc": o.company.cnae_desc, "company_size": o.company.company_size,
    }


def serialize_company(c, opportunities: int = 0):
    return {
        "id": c.id, "name": c.name, "trade_name": c.trade_name, "cnpj": c.cnpj, "cnpj_formatted": format_cnpj(c.cnpj) if c.cnpj else None,
        "segment": c.segment, "city": c.city, "state": c.state, "cnae_main": c.cnae_main, "cnae_desc": c.cnae_desc,
        "registration_status": c.registration_status, "company_size": c.company_size, "legal_nature": c.legal_nature,
        "capital_social": c.capital_social, "opened_at": c.opened_at, "target_profile": c.target_profile,
        "target_profile_label": SEGMENTS.get(c.target_profile, {}).get("label"),
        "registry_source": c.registry_source, "registry_updated_at": iso(c.registry_updated_at),
        "opportunities": opportunities,
    }


@router.get("/health")
def health():
    return {"status": "ok", "service": "LeadCob AI", "version": "0.3.0"}


@router.get("/dashboard/summary")
def summary(db: Session = Depends(get_db)):
    active = lambda: db.query(Opportunity).filter(Opportunity.status != "discarded")
    count = lambda **kw: active().filter_by(**kw).count()
    avg = active().with_entities(func.avg(Opportunity.score)).scalar() or 0
    return {
        "total": active().count(), "hiring": count(kind="hiring"), "outsourcing": count(kind="outsourcing"),
        "public_procurement": count(kind="public_procurement"), "qualified": count(status="qualified"),
        "proven": count(commercial_signal="oportunidade_comprovada"),
        "to_confirm": count(kind="public_procurement", commercial_signal="sinal_a_confirmar"),
        "open_procurements": count(kind="public_procurement", opportunity_class="edital_aberto"),
        "prospects": db.query(Company).filter(Company.target_profile.isnot(None)).count(),
        "average_score": round(avg, 1),
    }


@router.get("/opportunities")
def list_opportunities(kind: str | None = None, status: str | None = None, signal: str | None = None,
                       q: str | None = Query(default=None), db: Session = Depends(get_db)):
    query = db.query(Opportunity).options(joinedload(Opportunity.company))
    if kind in KINDS:
        query = query.filter(Opportunity.kind == kind)
    if status:
        query = query.filter(Opportunity.status == status)
    else:
        query = query.filter(Opportunity.status != "discarded")
    if signal in ("oportunidade_comprovada", "sinal_a_confirmar"):
        query = query.filter(Opportunity.commercial_signal == signal)
    if q:
        query = query.join(Company).filter(Company.name.ilike(f"%{q}%") | Opportunity.title.ilike(f"%{q}%"))
    rows = query.order_by(Opportunity.score.desc(), Opportunity.collected_at.desc()).limit(250).all()
    return [serialize(o) for o in rows]


@router.post("/opportunities")
def create_opportunity(payload: OpportunityCreate, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.cnpj == payload.cnpj).first() if payload.cnpj else None
    if not company:
        company = Company(name=payload.company_name, cnpj=payload.cnpj, segment=payload.segment, city=payload.city,
                          state=payload.state, website=payload.website, institutional_email=payload.institutional_email)
        db.add(company); db.flush()
    score, reason = score_opportunity(payload.kind, payload.description, payload.evidence, payload.source_url)
    o = Opportunity(company_id=company.id, kind=payload.kind, title=payload.title, description=payload.description,
                    evidence=payload.evidence, source_name=payload.source_name, source_url=payload.source_url,
                    score=score, score_reason=reason, status="review", confidence=0.45, is_verified=False,
                    commercial_signal="sinal_a_confirmar")
    db.add(o); db.commit()
    o = db.query(Opportunity).options(joinedload(Opportunity.company)).filter_by(id=o.id).first()
    return serialize(o)


@router.post("/agents/run/{opportunity_id}")
def run_agents(opportunity_id: int, db: Session = Depends(get_db)):
    o = db.query(Opportunity).options(joinedload(Opportunity.company)).filter_by(id=opportunity_id).first()
    if not o:
        raise HTTPException(404, "Oportunidade não encontrada")
    result = run_pipeline(db, o)
    return {"opportunity": serialize(o), "agents": result}


SOURCES_FILE = Path(__file__).resolve().parents[3] / "config" / "sources.json"


@router.get("/sources")
def sources(category: str | None = Query(default=None, pattern="^(integrada|consultada|planejada)$")):
    """Catálogo de fontes: integradas (testadas com dados reais), consultadas e planejadas."""
    data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    items = [s for s in data["sources"] if not category or s["category"] == category]
    try:
        boards = len(jobboards.configured_boards())
    except ValueError:
        boards = None
    return {"verified_at": data["verified_at"], "legend": data["legend"], "job_boards_configured": boards, "sources": items}


# ------------------------------------------------------------------ captação
def source_key_for(item):
    if item.get("control"):
        return "pncp:" + item["control"]
    raw = item["company_name"] + item["object"] + (item.get("published") or "")
    return "pncp:hash:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def evidence_text(item):
    parts = [
        f"Objeto (PNCP): {item['object'] or 'não informado'}",
        f"Controle PNCP: {item.get('control') or 'não informado'}",
        f"Modalidade: {item.get('modality_name') or item.get('modality_id') or 'não informada'}",
        f"Situação: {item.get('situation') or 'não informada'}",
        f"Publicação: {item.get('published') or 'não informada'}",
        f"Prazo: {item['class_reason']}",
        f"Aderência: {item['relevance']} — {item['relevance_reason']}",
        f"Evidência: {'confirmada na API oficial de consulta' if item['evidence_level'] == 'confirmada_api_oficial' else 'indício do índice de busca, sem confirmação na API oficial'}",
        f"Termos que localizaram o registro: {', '.join(item.get('matched_terms') or [])}",
    ]
    return " | ".join(parts) + "."


def apply_item(o, item):
    score, reason = score_procurement(item)
    proven = item["commercial_signal"] == "oportunidade_comprovada"
    o.title = item["title"]
    o.description = ("Edital aberto, aderente e confirmado na API oficial. Ler o edital (habilitação, escopo, prazo, "
                     "remuneração) antes de decidir participar." if proven else
                     "Sinal comercial a confirmar: verificar aderência do objeto, prazo e documentação no edital.")
    o.evidence = evidence_text(item)
    o.source_name = "PNCP — API oficial" if item["evidence_level"] == "confirmada_api_oficial" else "PNCP — busca do portal"
    o.source_url = item["url"]
    o.origin_url = item.get("origin_url")
    o.score, o.score_reason = score, reason
    o.relevance, o.relevance_reason = item["relevance"], item["relevance_reason"]
    o.opportunity_class, o.evidence_level = item["opportunity_class"], item["evidence_level"]
    o.commercial_signal = item["commercial_signal"]
    o.deadline = parse_dt(item.get("deadline"))
    try:
        value = float(item["estimated_value"]) if item.get("estimated_value") not in (None, "") else None
        o.estimated_value = value if value else None  # o PNCP usa 0 quando não há valor estimado
    except (TypeError, ValueError):
        o.estimated_value = None
    o.modality_name = item.get("modality_name")
    o.confidence = 0.8 if proven else (0.6 if item["evidence_level"] == "confirmada_api_oficial" else 0.35)
    o.is_verified = False  # verificação humana do edital continua obrigatória


@router.post("/capture/pncp")
def capture_pncp(mode: str = Query(default="busca", pattern="^(busca|varredura)$"),
                 only_open: bool = True, include_review: bool = True,
                 max_pages: int = Query(default=2, ge=1, le=5), days: int = Query(default=7, ge=1, le=30),
                 db: Session = Depends(get_db)):
    run = CaptureRun(source_name=f"PNCP — {mode}", status="running")
    db.add(run); db.commit(); db.refresh(run)
    try:
        if mode == "busca":
            batch = pncp.search_opportunities(only_open=only_open, max_pages=max_pages)
        else:
            batch = pncp.scan_publications(days=days, max_pages=max_pages)
    except Exception as exc:  # erro inesperado do coletor
        batch = {"records": [], "pages_read": 0, "errors": [f"{type(exc).__name__}: {str(exc)[:300]}"], "confirmed": 0}

    if batch["pages_read"] == 0:
        run.status = "failed"
        run.message = "Nenhuma página do PNCP foi lida. " + " ; ".join(batch["errors"][:5])
        run.finished_at = datetime.now(timezone.utc); db.commit()
        raise HTTPException(status_code=502, detail="O PNCP não respondeu. A API costuma limitar rajadas de consultas; tente novamente em alguns minutos.")

    created = updated = discarded = 0
    discarded_samples = []
    keep = {"alta", "revisar"} if include_review else {"alta"}
    for item in batch["records"]:
        key = source_key_for(item)
        o = db.query(Opportunity).filter_by(source_key=key).first()
        if item["relevance"] not in keep:
            discarded += 1
            if len(discarded_samples) < 10:
                discarded_samples.append({"orgao": item["company_name"], "objeto": item["object"][:160], "motivo": item["relevance_reason"]})
            if o and o.status != "discarded":  # reclassificado após ajuste das regras
                apply_item(o, item)
                o.status, o.commercial_signal = "discarded", "descartado"
            continue
        if o:
            updated += 1
        else:
            company = db.query(Company).filter_by(cnpj=item["cnpj"]).first() if item["cnpj"] else None
            if not company:
                company = Company(name=item["company_name"], cnpj=item["cnpj"], segment="Órgão público",
                                  city=item["city"], state=item["state"])
                db.add(company); db.flush()
            o = Opportunity(company_id=company.id, kind="public_procurement", source_key=key, status="review")
            db.add(o); created += 1
        apply_item(o, item)

    stored = [r for r in batch["records"] if r["relevance"] in keep]
    proven = sum(1 for r in stored if r["commercial_signal"] == "oportunidade_comprovada")
    run.status = "partial" if batch["errors"] else "completed"
    run.records_seen = len(batch["records"]); run.records_created = created; run.records_skipped = discarded
    notes = [f"modo {mode}", f"páginas lidas: {batch['pages_read']}", f"confirmados na API oficial: {batch.get('confirmed', 0)}",
             f"atualizados: {updated}", f"descartados por aderência: {discarded}"]
    if batch.get("coverage_note"):
        notes.append(batch["coverage_note"])
    if batch["errors"]:
        notes.append(f"falhas parciais ({len(batch['errors'])}): " + " ; ".join(batch["errors"][:3]))
    run.message = "; ".join(notes)[:4000]
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    return {"run_id": run.id, "status": run.status, "source": "PNCP", "mode": mode, "pages_read": batch["pages_read"],
            "found": len(batch["records"]), "confirmed": batch.get("confirmed", 0), "created": created, "updated": updated,
            "discarded": discarded, "proven": proven, "to_confirm": len(stored) - proven,
            "discarded_samples": discarded_samples, "errors": batch["errors"][:10], "message": run.message,
            "duplicates_skipped": updated}  # compatibilidade com o frontend v0.2


@router.get("/capture/runs")
def capture_runs(db: Session = Depends(get_db)):
    rows = db.query(CaptureRun).order_by(CaptureRun.started_at.desc()).limit(20).all()
    return [{"id": r.id, "source_name": r.source_name, "status": r.status, "records_seen": r.records_seen,
             "records_created": r.records_created, "records_skipped": r.records_skipped, "message": r.message,
             "started_at": iso(r.started_at), "finished_at": iso(r.finished_at)} for r in rows]


# ---------------------------------------------------------------------- CNPJ
def _lookup_or_http_error(cnpj: str) -> dict:
    try:
        return cnpj_api.lookup(cnpj)
    except cnpj_api.CNPJInvalid as exc:
        raise HTTPException(400, str(exc))
    except cnpj_api.CNPJNotFound as exc:
        raise HTTPException(404, str(exc))
    except cnpj_api.CNPJUnavailable:
        raise HTTPException(502, "BrasilAPI e Minha Receita não responderam. Tente novamente em instantes.")


@router.get("/cnpj/{cnpj}")
def cnpj_lookup(cnpj: str):
    """Consulta sem gravar (para preencher formulários)."""
    data = _lookup_or_http_error(cnpj)
    data["cnpj_formatted"] = format_cnpj(data["cnpj"])
    data["target_profile"] = profile_for(data.get("cnae_principal"))
    return data


@router.post("/companies/{company_id}/enrich")
def enrich_company(company_id: int, db: Session = Depends(get_db)):
    from app.jobs.import_cnpj import apply_registry
    c = db.query(Company).filter_by(id=company_id).first()
    if not c:
        raise HTTPException(404, "Empresa não encontrada")
    if not c.cnpj:
        raise HTTPException(400, "Empresa sem CNPJ cadastrado")
    data = _lookup_or_http_error(c.cnpj)
    data["target_profile"] = c.target_profile or profile_for(data.get("cnae_principal"))
    apply_registry(c, data, source=f"{data['source']} (dados abertos da Receita Federal)")
    db.commit(); db.refresh(c)
    return serialize_company(c, len(c.opportunities))


@router.get("/segments")
def segments():
    return [{"key": k, **v} for k, v in SEGMENTS.items()]


@router.get("/prospects")
def prospects(segment: str | None = None, uf: str | None = None, q: str | None = None, cnae: str | None = None,
              size: str | None = Query(default=None, description="MICRO EMPRESA | EMPRESA DE PEQUENO PORTE | DEMAIS"),
              min_capital: float | None = None, include_competitors: bool = False,
              limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)):
    """Base de empresas-alvo: cadastro por perfil de CNAE — NÃO é sinal de demanda."""
    query = db.query(Company, func.count(Opportunity.id)).outerjoin(Opportunity).filter(Company.target_profile.isnot(None))
    if cnae:
        query = query.filter(Company.cnae_main.like(re.sub(r"\D", "", cnae) + "%"))
    if size:
        query = query.filter(Company.company_size == size.upper())
    if min_capital is not None:
        query = query.filter(Company.capital_social >= min_capital)
    if not include_competitors:
        query = query.filter((Company.cnae_main.is_(None)) | (~Company.cnae_main.like(COMPETITOR_CNAE + "%")))
    if segment:
        query = query.filter(Company.target_profile == segment)
    if uf:
        query = query.filter(Company.state == uf.upper())
    if q:
        digits = clean_cnpj(q)
        cond = Company.name.ilike(f"%{q}%") | Company.trade_name.ilike(f"%{q}%")
        if digits:
            cond = cond | Company.cnpj.like(f"{digits}%")
        query = query.filter(cond)
    rows = query.group_by(Company.id).order_by(Company.capital_social.desc().nullslast(), Company.name).limit(limit).all()
    return [serialize_company(c, n) for c, n in rows]


# -------------------------------------------------------------------- vagas
ROLE_LABEL = {"operacao_interna": "equipe própria de cobrança (argumento: terceirizar/complementar)",
              "estrategia_dados": "área de recuperação estruturada (argumento: credenciamento como assessoria)"}


def _company_for_job(db: Session, item: dict):
    company = db.query(Company).filter_by(cnpj=item["cnpj"]).first() if item["cnpj"] else None
    if not company and not item["cnpj"]:
        company = db.query(Company).filter(func.lower(Company.name) == item["company_name"].lower()).first()
    if not company:
        board = item["board"]
        company = Company(name=item["company_name"], cnpj=item["cnpj"], segment=board.get("segment"),
                          city=board.get("city"), state=(board.get("state") or None))
        db.add(company); db.flush()
    if company.cnpj and not company.cnae_main:  # melhor esforço: CNAE revela concorrentes
        try:
            from app.jobs.import_cnpj import apply_registry
            data = cnpj_api.lookup(company.cnpj)
            apply_registry(company, data, source=f"{data['source']} (dados abertos da Receita Federal)")
        except Exception:
            pass
    return company


@router.post("/capture/jobs")
def capture_jobs(db: Session = Depends(get_db)):
    try:
        batch = jobboards.fetch_job_opportunities()
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not batch["boards_configured"]:
        raise HTTPException(400, "Nenhum board configurado (config/job_boards.json ou JOB_BOARD_SOURCES_JSON).")
    run = CaptureRun(source_name="Greenhouse / Lever — career boards públicos", status="running")
    db.add(run); db.commit(); db.refresh(run)
    created = updated = closed = competitors = 0
    seen_keys = set()
    for item in batch["records"]:
        company = _company_for_job(db, item)
        item["competitor"] = bool(company.cnae_main and company.cnae_main.startswith(COMPETITOR_CNAE))
        competitors += item["competitor"]
        item["cnpj"] = company.cnpj
        key = item["source_key"]; seen_keys.add(key)
        o = db.query(Opportunity).filter_by(source_key=key).first()
        if o:
            updated += 1
        else:
            o = Opportunity(company_id=company.id, kind="hiring", source_key=key, status="review"); db.add(o); created += 1
        score, reason = score_job(item)
        provider = "Greenhouse" if item["provider"] == "greenhouse" else "Lever"
        o.title = item["title"]
        o.description = item["description"][:5000] or item["title"]
        o.evidence = (f"Vaga publicada no board {provider} '{item['board']['token']}' ({item['company_name']}) | "
                      f"Local: {item['location'] or 'não informado'} | Publicação: {item['published'] or 'não informada'} | "
                      f"Leitura: {ROLE_LABEL.get(item['role_type'], item['role_type'])} | {item['relevance_reason']}"
                      + (" | ATENÇÃO: empresa do ramo de cobrança — concorrente" if item["competitor"] else "")
                      + ". Vaga indica contratação interna; não comprova intenção de terceirizar.")
        o.source_name = f"{provider} — career board público"
        o.source_url = item["url"]
        o.score, o.score_reason = score, reason
        o.relevance, o.relevance_reason = ("descartar" if item["competitor"] else item["relevance"]), item["relevance_reason"]
        o.opportunity_class = "concorrente" if item["competitor"] else item["role_type"]
        o.evidence_level, o.commercial_signal = "fonte_primaria", "sinal_a_confirmar"
        o.modality_name, o.confidence, o.is_verified = provider, 0.7, False
    # Vagas que sumiram de um board consultado com sucesso: encerradas (histórico preservado).
    for prefix in batch["boards_fetched"]:
        for o in db.query(Opportunity).filter(Opportunity.source_key.like(prefix + "%")).all():
            if o.source_key not in seen_keys and o.opportunity_class != "vaga_encerrada":
                o.opportunity_class = "vaga_encerrada"; o.score = max(0, o.score - 15); closed += 1
    run.status = "partial" if batch["errors"] else "completed"
    run.records_seen = batch["jobs_read"]; run.records_created = created; run.records_skipped = len(batch["discarded_samples"])
    run.message = (f"boards: {batch['boards_configured']} configurados, {len(batch['boards_fetched'])} lidos; "
                   f"vagas lidas: {batch['jobs_read']}; aderentes: {len(batch['records'])}; novas: {created}; "
                   f"atualizadas: {updated}; encerradas: {closed}; concorrentes: {competitors}; falhas: {len(batch['errors'])}")
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    return {"run_id": run.id, "status": run.status, "boards_configured": batch["boards_configured"],
            "boards_fetched": len(batch["boards_fetched"]), "jobs_read": batch["jobs_read"], "matches": len(batch["records"]),
            "created": created, "updated": updated, "closed": closed, "competitors": competitors,
            "discarded_samples": batch["discarded_samples"], "errors": batch["errors"], "message": run.message}
