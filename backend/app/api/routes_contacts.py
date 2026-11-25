"""Diretório institucional vinculado a CNPJs, com coleta rastreável e opt-out."""
from datetime import datetime, timezone
from urllib.parse import urlparse, urlencode
import re
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from app.db.database import get_db
from app.db.models import BusinessContact, Company, Suppression, AuditLog, DomainCandidate
from app.services.contactability import build_map as build_contact_map, department_from_email
from app.services.contact_suppression import is_suppressed, suppression_keys, sql_cnpj

router = APIRouter(prefix="/api/contacts", tags=["contatos empresariais"])
KINDS = {"email", "website", "phone", "whatsapp", "linkedin", "instagram", "facebook"}
STATUSES = {"a_verificar", "verificado", "invalido"}

class ContactIn(BaseModel):
    company_id: int
    kind: str
    value: str = Field(min_length=3, max_length=500)
    department: str = Field(default="geral", max_length=40)
    source_name: str = Field(min_length=2, max_length=120)
    source_url: str | None = None

def is_blocked(db, company):
    return is_suppressed(db, company)

def clean(kind, value):
    v = value.strip()
    if kind == "email":
        v = v.lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", v): raise HTTPException(422, "E-mail inválido")
    elif kind in {"website", "linkedin", "instagram", "facebook"}:
        u = urlparse(v)
        if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
            raise HTTPException(422, "Site deve ter URL HTTP(S) válida")
        if kind != "website":
            from app.collectors.site_contacts import published_channels
            matches = [x for x in published_channels(f'<a href="{escape(v, quote=True)}">', v) if x["kind"] == kind]
            if not matches:
                raise HTTPException(422, "Informe a página corporativa da rede selecionada")
            v = matches[0]["value"]
    elif kind in {"phone", "whatsapp"}:
        digits = re.sub(r"\D", "", v)
        if not 10 <= len(digits) <= 13: raise HTTPException(422, "Telefone empresarial inválido")
        v = "55" + digits if kind == "whatsapp" and len(digits) in (10, 11) else digits
    else: raise HTTPException(422, "Tipo de contato inválido")
    return v

def serialize(x, company=None):
    c = company or x.company
    return {"id": x.id, "company_id": x.company_id, "company_name": c.name, "cnpj": c.cnpj,
            "kind": x.kind, "value": x.value, "department": x.department, "city": c.city, "state": c.state,
            "source_name": x.source_name, "source_url": x.source_url, "status": x.status,
            "created_at": x.created_at.isoformat(), "checked_at": x.checked_at.isoformat() if x.checked_at else None}

def insert(db, company, kind, value, source, url=None, department=None, status="a_verificar"):
    if not value or is_blocked(db, company): return False
    v = clean(kind, value)
    existing = db.query(BusinessContact).filter_by(company_id=company.id, kind=kind, value=v).first()
    if existing:
        if existing.department == "geral" and department and department != "geral": existing.department = department
        if existing.status != "verificado" and status == "verificado": existing.status = "verificado"
        return False
    dep = department or (department_from_email(v) if kind == "email" else "geral")
    db.add(BusinessContact(company_id=company.id, kind=kind, value=v, source_name=source, source_url=url,
                           department=dep, status=status))
    return True

@router.get("")
def list_contacts(q: str = "", kind: str = "", company_id: int | None = None, status: str = "", uf: str = "", city: str = "", limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    query = db.query(BusinessContact, Company).join(Company, BusinessContact.company_id == Company.id)
    blocked_ids, blocked_cnpjs = suppression_keys(db)
    if blocked_ids:
        query = query.filter(~Company.id.in_(blocked_ids))
    if blocked_cnpjs:
        query = query.filter(or_(Company.cnpj.is_(None), ~sql_cnpj(Company.cnpj).in_(blocked_cnpjs)))
    if uf: query = query.filter(func.upper(Company.state) == uf.strip().upper())
    if city: query = query.filter(Company.city.ilike(f"%{city.strip()}%"))
    if status in STATUSES: query = query.filter(BusinessContact.status == status)
    if company_id: query = query.filter(BusinessContact.company_id == company_id)
    if q: query = query.filter(or_(Company.name.ilike(f"%{q}%"), Company.cnpj.ilike(f"%{q}%"), BusinessContact.value.ilike(f"%{q}%")))
    available = query.filter(BusinessContact.status != "invalido")
    coverage = {k: n for k, n in available.with_entities(BusinessContact.kind, func.count(func.distinct(Company.id))).group_by(BusinessContact.kind).all()}
    if kind in KINDS: query = query.filter(BusinessContact.kind == kind)
    total = query.count()
    rows = query.order_by(BusinessContact.id.desc()).offset(offset).limit(limit).all()
    return {"total": total, "companies_by_channel": coverage, "items": [serialize(x, c) for x,c in rows]}

@router.post("", status_code=201)
def add_contact(payload: ContactIn, db: Session = Depends(get_db)):
    c = db.get(Company, payload.company_id)
    if not c: raise HTTPException(404, "Empresa não encontrada")
    if is_blocked(db, c): raise HTTPException(403, "Empresa em lista de supressão")
    if payload.kind not in KINDS: raise HTTPException(422, "Tipo inválido")
    value = clean(payload.kind, payload.value)
    if db.query(BusinessContact).filter_by(company_id=c.id, kind=payload.kind, value=value).first():
        raise HTTPException(409, "Contato já cadastrado")
    item = BusinessContact(company_id=c.id, kind=payload.kind, value=value, source_name=payload.source_name, source_url=payload.source_url, department=payload.department)
    db.add(item); db.flush()
    db.add(AuditLog(event="contact_added", entity_type="business_contact", entity_id=item.id, details={"company_id": c.id, "source": item.source_name}))
    db.commit(); db.refresh(item)
    return serialize(item, c)

@router.post("/sync")
def sync_contacts(limit: int = Query(500, ge=1, le=2000), after_id: int = Query(0, ge=0), db: Session = Depends(get_db)):
    """Importa apenas canais institucionais JÁ presentes na ficha, sem inferir contatos."""
    count = 0; scanned = 0
    last_id = after_id
    for c in db.query(Company).filter(Company.id > after_id).filter(or_(Company.website.isnot(None), Company.institutional_email.isnot(None))).order_by(Company.id).limit(limit):
        scanned += 1
        last_id = c.id
        for kind, value in (("website", c.website), ("email", c.institutional_email)):
            try:
                if insert(db, c, kind, value, "Ficha empresarial existente"): count += 1
            except HTTPException: pass
    db.add(AuditLog(event="contacts_sync", entity_type="business_contact", entity_id=None, details={"scanned": scanned, "added": count}))
    db.commit()
    return {"scanned": scanned, "added": count, "next_cursor": last_id if scanned == limit else None, "note": "Sincronização de canais existentes; não houve pesquisa externa"}

@router.patch("/{contact_id}/verify")
def verify(contact_id: int, status: str = Query(pattern="^(verificado|invalido|a_verificar)$"), db: Session = Depends(get_db)):
    item = db.get(BusinessContact, contact_id)
    if not item: raise HTTPException(404, "Contato não encontrado")
    if is_blocked(db, db.get(Company, item.company_id)): raise HTTPException(403, "Empresa em lista de supressão")
    company = db.get(Company, item.company_id)
    if status == "invalido":
        field = {"email": "institutional_email", "website": "website"}.get(item.kind)
        if field and (getattr(company, field) or "").strip().lower() == item.value.lower():
            setattr(company, field, None)
    item.status = status
    item.checked_at = datetime.now(timezone.utc)
    db.add(AuditLog(event="contact_reviewed", entity_type="business_contact", entity_id=item.id, details={"status": status}))
    db.commit()
    return {"id": item.id, "status": item.status}


@router.post("/discover/{company_id}")
def discover_from_site(company_id: int, db: Session = Depends(get_db)):
    """Lê o site oficial cadastrado na ficha e guarda e-mails institucionais do próprio domínio (a verificar)."""
    from app.collectors import site_contacts
    c = db.get(Company, company_id)
    if not c: raise HTTPException(404, "Empresa não encontrada")
    if is_blocked(db, c): raise HTTPException(403, "Empresa em lista de supressão")
    if not c.website: raise HTTPException(400, "Cadastre primeiro o site institucional da empresa (confirmado por você) na ficha.")
    try:
        result = site_contacts.discover(c.website)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    added = 0
    for item in result["emails"]:
        try:
            if insert(db, c, "email", item["email"], "Site institucional (leitura automática)", item["source_url"], department_from_email(item["email"])): added += 1
        except HTTPException:
            pass
    for item in result.get("channels", []):
        try:
            if insert(db, c, item["kind"], item["value"], "Site institucional (leitura automática)", item["source_url"]):
                added += 1
        except HTTPException:
            pass
    db.flush()
    if not c.institutional_email:
        email = db.query(BusinessContact).filter_by(company_id=c.id, kind="email").filter(
            BusinessContact.status != "invalido").order_by(BusinessContact.id).first()
        if email:
            c.institutional_email = email.value
    db.add(AuditLog(event="contacts_discovered", entity_type="company", entity_id=c.id,
                    details={"pages": result["pages_read"], "found": len(result["emails"]) + len(result.get("channels", [])), "added": added}))
    db.commit()
    return {**result, "added": added,
            "note": "Canais publicados no site institucional cadastrado, com origem registrada. Confira antes de usar (status: a verificar)."}


@router.get("/map/{company_id}")
def contact_map(company_id: int, db: Session = Depends(get_db)):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(404, "Empresa não encontrada")
    if is_blocked(db, c):
        raise HTTPException(403, "Empresa em lista de supressão")
    contacts = db.query(BusinessContact).filter_by(company_id=c.id).all()
    opportunities = getattr(c, "opportunities", [])
    return build_contact_map(c, contacts, opportunities)


@router.post("/enrich/{company_id}")
def enrich_contact_map(company_id: int, db: Session = Depends(get_db)):
    """Enriquece apenas canais institucionais e devolve o mapa de contato atualizado."""
    from app.core.config import settings
    from app.collectors import site_contacts
    from app.services.domain_search import search

    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(404, "Empresa não encontrada")
    if is_blocked(db, c):
        raise HTTPException(403, "Empresa em lista de supressão")

    added = 0
    candidates = []
    search_notes = []

    if c.website:
        try:
            if insert(db, c, "website", c.website, "Ficha empresarial existente"):
                added += 1
        except HTTPException:
            pass
    if c.institutional_email:
        try:
            if insert(db, c, "email", c.institutional_email, "Ficha empresarial existente",
                      department=department_from_email(c.institutional_email)):
                added += 1
        except HTTPException:
            pass

    if not c.website and settings.brave_search_api_key:
        try:
            found = search(c, settings.brave_search_api_key)
        except Exception:
            found = []
            search_notes.append("Pesquisa automática indisponível; nenhum domínio foi confirmado.")
        for result in found:
            current = db.query(DomainCandidate).filter_by(company_id=c.id, website=result["website"]).first()
            if not current:
                current = DomainCandidate(company_id=c.id, **result)
                db.add(current); db.flush()
            else:
                current.source_url = result["source_url"]
                current.evidence = result["evidence"]
                current.status = result["status"]
            candidates.append({"id": current.id, "website": current.website,
                               "source_url": current.source_url, "evidence": current.evidence,
                               "status": current.status})

        exact = [x for x in candidates if x["status"] == "cnpj_no_site"]
        if len(exact) == 1:
            c.website = exact[0]["website"]
            candidate = db.get(DomainCandidate, exact[0]["id"])
            candidate.status = "verificado"
            candidate.checked_at = datetime.now(timezone.utc)
            if insert(db, c, "website", c.website, "Site oficial confirmado por CNPJ",
                      exact[0]["source_url"], status="verificado"):
                added += 1

    discovered = {"pages_read": [], "emails": [], "channels": [], "notes": []}
    if c.website:
        try:
            discovered = site_contacts.discover(c.website)
            for item in discovered["emails"]:
                if insert(db, c, "email", item["email"], "Site institucional (leitura automática)",
                          item["source_url"], department_from_email(item["email"])):
                    added += 1
            for item in discovered.get("channels", []):
                if insert(db, c, item["kind"], item["value"], "Site institucional (leitura automática)",
                          item["source_url"]):
                    added += 1
        except ValueError as exc:
            discovered["notes"].append(str(exc))

    if not c.institutional_email:
        email = db.query(BusinessContact).filter_by(company_id=c.id, kind="email").filter(
            BusinessContact.status != "invalido").order_by(BusinessContact.status.desc(), BusinessContact.id).first()
        if email:
            c.institutional_email = email.value

    db.add(AuditLog(event="contact_map_enriched", entity_type="company", entity_id=c.id,
                    details={"added": added, "domain_candidates": len(candidates),
                             "pages_read": len(discovered.get("pages_read", []))}))
    db.commit()

    contacts = db.query(BusinessContact).filter_by(company_id=c.id).all()
    result = build_contact_map(c, contacts, getattr(c, "opportunities", []))
    if not c.website and not settings.brave_search_api_key:
        query = f'"{c.name}" "{c.cnpj or ""}" site oficial contato'
        result["site_search_url"] = "https://duckduckgo.com/?" + urlencode({"q": query})
        result["automatic_site_search"] = False
    else:
        result["automatic_site_search"] = bool(settings.brave_search_api_key)
    result["domain_candidates"] = candidates
    result["added"] = added
    result["pages_read"] = discovered.get("pages_read", [])
    result["notes"] = search_notes + discovered.get("notes", [])
    return result


@router.post('/domain-search/{company_id}')
def search_domain(company_id: int, db: Session = Depends(get_db)):
    from app.core.config import settings
    from app.db.models import DomainCandidate
    from app.services.domain_search import search
    c = db.get(Company, company_id)
    if not c or is_blocked(db, c):
        raise HTTPException(404, 'Empresa indisponível.')
    if not settings.brave_search_api_key:
        query = f'"{c.name}" "{c.cnpj or ""}" site oficial contato'
        return {
            'items': [], 'automatic_available': False,
            'search_url': 'https://duckduckgo.com/?' + urlencode({'q': query}),
            'note': 'A pesquisa automática de sites está indisponível. Abra a pesquisa pública, confira o site da empresa e salve-o na ficha para buscar os canais publicados.',
        }
    try:
        results = search(c, settings.brave_search_api_key)
    except Exception as exc:
        # Details from the search service may contain the key or internal URLs.
        raise HTTPException(502, 'Pesquisa de domínios indisponível. Tente novamente depois.') from exc
    items = []
    for result in results:
        current = db.query(DomainCandidate).filter_by(company_id=c.id, website=result['website']).first()
        if not current:
            current = DomainCandidate(company_id=c.id, **result)
            db.add(current)
            db.flush()
        else:
            current.source_url, current.evidence, current.status = result['source_url'], result['evidence'], result['status']
        items.append({'id': current.id, 'website': current.website, 'source_url': current.source_url,
                      'evidence': current.evidence, 'status': current.status})
    db.add(AuditLog(event='domain_search', entity_type='company', entity_id=c.id, details={'candidates': len(items)}))
    db.commit()
    return {'items': items, 'note': 'Confira a fonte e o site antes de selecionar o domínio.'}


@router.post('/domain-candidates/{candidate_id}/confirm')
def confirm_domain(candidate_id: int, db: Session = Depends(get_db)):
    from app.db.models import DomainCandidate
    candidate = db.get(DomainCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, 'Candidato não encontrado.')
    company = db.get(Company, candidate.company_id)
    if not company or is_blocked(db, company):
        raise HTTPException(403, 'Empresa indisponível.')
    if candidate.status == 'verificado':
        return {'website': candidate.website, 'reused': True}
    previous = company.website
    company.website = candidate.website
    candidate.status = 'verificado'
    candidate.checked_at = datetime.now(timezone.utc)
    db.add(AuditLog(event='domain_confirmed', entity_type='company', entity_id=company.id,
                    details={'from': previous, 'to': candidate.website, 'source': candidate.source_url,
                             'evidence': candidate.evidence}))
    db.commit()
    return {'website': candidate.website}


class ReviewedSiteIn(BaseModel):
    website: str = Field(min_length=8, max_length=500)
    source_url: str = Field(min_length=8, max_length=1000)
    evidence: str = Field(min_length=12, max_length=1000)
    ownership_reviewed: bool = False


@router.post("/reviewed-site/{company_id}")
def register_reviewed_site(company_id: int, payload: ReviewedSiteIn, db: Session = Depends(get_db)):
    """Owner explicitly records a reviewed institutional site; no external fetch."""
    from app.services.cnpj import clean_cnpj, is_valid_cnpj
    from app.services.contact_readiness import corporate_identity
    from app.services.safe_http import validate_url

    if not payload.ownership_reviewed:
        raise HTTPException(422, "Confirme a titularidade do site com base em fonte pública.")
    website = payload.website.strip().rstrip("/")
    source = payload.source_url.strip()
    evidence = payload.evidence.strip()
    try:
        validate_url(website)
        validate_url(source)
        if len(evidence) < 12:
            raise ValueError("Evidência insuficiente.")
    except ValueError as exc:
        raise HTTPException(422, "Informe URLs públicas válidas e evidência da titularidade.") from exc

    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Empresa não encontrada.")
    if is_blocked(db, company):
        raise HTTPException(403, "Empresa em lista de supressão.")
    cnpj = clean_cnpj(company.cnpj)
    if not is_valid_cnpj(cnpj):
        raise HTTPException(422, "CNPJ inválido.")
    # Do not replace an existing or conflicting site via this initial-registration flow.
    peers = db.query(Company).filter(sql_cnpj(Company.cnpj) == cnpj).all()
    if not peers or any(
        str(peer.registration_status or "").strip().upper() != "ATIVA"
        or not corporate_identity(peer.legal_nature, peer.name)
        for peer in peers
    ):
        raise HTTPException(422, "Cadastro empresarial inconsistente; revise a ficha.")
    if any(str(peer.website or "").strip().rstrip("/") not in ("", website) for peer in peers):
        raise HTTPException(409, "Site já cadastrado ou conflitante; revise a ficha antes de substituir.")
    candidate = db.query(DomainCandidate).filter_by(company_id=company_id, website=website).first()
    if candidate is None:
        candidate = DomainCandidate(company_id=company_id, website=website,
                                    source_url=source, evidence=evidence)
        db.add(candidate)
    candidate.source_url = source
    candidate.evidence = evidence
    candidate.status = "verificado"
    candidate.checked_at = datetime.now(timezone.utc)
    company.website = website
    # Review of ownership is not a verification of direct contact channels.
    db.add(AuditLog(event="domain_reviewed_manually", entity_type="company", entity_id=company_id,
                    details={"website": website, "source": source, "evidence": evidence}))
    db.commit()
    return {"website": website, "ownership_reviewed": True, "external_check": False,
            "note": "Revisão declarada pelo proprietário. Nenhuma coleta executada."}


class BatchDiscoveryIn(BaseModel):
    company_ids: list[int] = Field(min_length=1, max_length=5)


@router.post('/discover-batch')
def discover_batch(payload: BatchDiscoveryIn, db: Session = Depends(get_db)):
    """Bounded manual batch of official sites. Each company commits independently."""
    from app.collectors import site_contacts
    from app.services.safe_http import validate_url
    from app.services.cnpj import is_valid_cnpj
    import httpx
    results = []
    for company_id in dict.fromkeys(payload.company_ids):
        row = {'company_id': company_id, 'added': 0, 'pages_read': 0}
        try:
            company = db.get(Company, company_id)
            if company is None:
                row['status'] = 'not_found'
            elif is_blocked(db, company):
                row['status'] = 'suppressed'
            elif not is_valid_cnpj(company.cnpj):
                row['status'] = 'invalid_cnpj'
            elif not company.website:
                row['status'] = 'missing_website'
            else:
                website = company.website
                validate_url(website if '://' in website else 'https://' + website)
                result = site_contacts.discover(website, max_pages=2)
                # Recheck opt-out after network work, before any insertion.
                db.expire_all()
                company = db.get(Company, company_id)
                if not company or is_blocked(db, company) or company.website != website:
                    row['status'] = 'changed_or_suppressed'
                else:
                    candidates = [('email', x['email'], x['source_url']) for x in result['emails']]
                    candidates += [(x['kind'], x['value'], x['source_url']) for x in result.get('channels', [])]
                    seen = set()
                    for kind, value, source in candidates[:100]:
                        try:
                            value = clean(kind, value)
                            validate_url(source)
                            key = (kind, value)
                            if key in seen:
                                continue
                            seen.add(key)
                            if insert(db, company, kind, value, 'Site institucional (lote)', source):
                                db.flush()
                                row['added'] += 1
                        except (HTTPException, ValueError):
                            continue
                    row['pages_read'] = len(result['pages_read'])
                    row['status'] = 'completed' if row['pages_read'] else 'unavailable'
                    db.add(AuditLog(event='contacts_batch_discovery', entity_type='company',
                                    entity_id=company_id, details=dict(row)))
                    db.commit()
        except (ValueError, httpx.HTTPError):
            db.rollback()
            row.update(status='unavailable', added=0)
        except Exception:
            db.rollback()
            row.update(status='error', added=0)
        results.append(row)
        db.rollback()
    return {'items': results, 'processed': len(results),
            'added': sum(r['added'] for r in results),
            'note': 'Somente sites cadastrados; contatos encontrados permanecem a verificar.'}


class DiscoveryQueueIn(BaseModel):
    company_ids: list[int] = Field(min_length=1,max_length=1000)


@router.post('/discovery-jobs', status_code=201)
def create_discovery_job(payload: DiscoveryQueueIn, db: Session = Depends(get_db)):
    from app.services.contact_discovery_queue import enqueue
    try:
        return {'job_id':enqueue(db,payload.company_ids)}
    except ValueError as exc:
        raise HTTPException(422,'Lista de empresas inválida.') from exc


@router.get('/discovery-jobs/{job_id}')
def get_discovery_job(job_id: int, db: Session = Depends(get_db)):
    from app.services.contact_discovery_queue import progress
    result=progress(db,job_id)
    if result is None:
        raise HTTPException(404,'Lote não encontrado.')
    return result


@router.get('/discovery-jobs/{job_id}/items')
def list_discovery_items(job_id: int, limit: int = Query(100,ge=1,le=250),
                         offset: int = Query(0,ge=0), db: Session = Depends(get_db)):
    from app.db.models import ContactDiscoveryItem, ContactDiscoveryJob
    if not db.get(ContactDiscoveryJob,job_id):
        raise HTTPException(404,'Lote não encontrado.')
    rows=db.query(ContactDiscoveryItem).filter_by(job_id=job_id).order_by(ContactDiscoveryItem.id).offset(offset).limit(limit)
    return [{'company_id':r.company_id,'status':r.status,'attempts':r.attempts,'result':r.result} for r in rows]


@router.get('/discovery-jobs')
def list_discovery_jobs(limit: int = Query(50,ge=1,le=100), offset: int = Query(0,ge=0),
                        db: Session = Depends(get_db)):
    from app.db.models import ContactDiscoveryJob, ContactDiscoveryItem
    jobs=db.query(ContactDiscoveryJob).order_by(ContactDiscoveryJob.id.desc()).offset(offset).limit(limit).all()
    if not jobs:
        return []
    counts={}
    for jid,status,count in db.query(ContactDiscoveryItem.job_id,ContactDiscoveryItem.status,func.count(ContactDiscoveryItem.id)).filter(
            ContactDiscoveryItem.job_id.in_([j.id for j in jobs])).group_by(ContactDiscoveryItem.job_id,ContactDiscoveryItem.status):
        counts.setdefault(jid,{})[status]=count
    return [{'job_id':j.id,'created_at':j.created_at.isoformat(),
             'total':sum(counts.get(j.id,{}).values()),
             **{k:counts.get(j.id,{}).get(k,0) for k in ('queued','running','completed','failed','skipped')}} for j in jobs]


@router.get('/coverage')
def contact_coverage(uf: str = Query('', max_length=2), city: str = Query('', max_length=100),
                     db: Session = Depends(get_db)):
    """Company-record coverage, not contact count or lead qualification."""
    from sqlalchemy import exists, and_
    blocked = exists().where(or_(Suppression.company_id == Company.id,
                                 and_(Company.cnpj.isnot(None), Suppression.cnpj == Company.cnpj)))
    scope = db.query(Company.id).filter(~blocked)
    if uf.strip():
        scope = scope.filter(func.upper(Company.state) == uf.strip().upper())
    if city.strip():
        scope = scope.filter(func.lower(Company.city) == city.strip().lower())
    eligible = scope.subquery()
    total = db.query(func.count()).select_from(eligible).scalar() or 0
    contacts = db.query(BusinessContact).join(eligible, BusinessContact.company_id == eligible.c.id).filter(
        BusinessContact.kind.in_(KINDS), BusinessContact.status.in_(['a_verificar', 'verificado']),
        func.length(func.trim(BusinessContact.value)) > 0,
        ~BusinessContact.value.like('anon:%'))
    available = dict(contacts.with_entities(BusinessContact.kind,func.count(func.distinct(BusinessContact.company_id)))
                     .group_by(BusinessContact.kind).all())
    verified = dict(contacts.filter(BusinessContact.status=='verificado')
                    .with_entities(BusinessContact.kind,func.count(func.distinct(BusinessContact.company_id)))
                    .group_by(BusinessContact.kind).all())
    any_channel = contacts.with_entities(func.count(func.distinct(BusinessContact.company_id))).scalar() or 0
    any_verified = contacts.filter(BusinessContact.status=='verificado').with_entities(
        func.count(func.distinct(BusinessContact.company_id))).scalar() or 0
    return {'eligible_company_records':total,'with_any_channel':any_channel,
            'without_registered_channel':total-any_channel,'with_any_verified_channel':any_verified,
            'channels':{kind:{'available':available.get(kind,0),'verified':verified.get(kind,0)}
                        for kind in sorted(KINDS)},
            'note':'Contagem de registros de empresas não suprimidos; apenas diretório cadastrado, não comprova ausência de contatos externos.'}


@router.get('/discovery-targets')
def discovery_targets(uf: str = Query('AM',pattern='^[A-Za-z]{2}$'),
                      city: str = Query('Manaus',min_length=1,max_length=100),
                      kind: str = Query('email',pattern='^(email|phone|whatsapp|linkedin|instagram|facebook|website)$'),
                      limit: int = Query(50,ge=1,le=100), offset: int = Query(0,ge=0),
                      db: Session = Depends(get_db)):
    from app.services.contact_targets import targets
    if not city.strip():
        raise HTTPException(422,'Município obrigatório.')
    return targets(db,uf.upper(),city.strip(),kind,limit,offset)


@router.get('/worker-diagnostics')
def worker_diagnostics(db: Session = Depends(get_db)):
    from app.services.contact_discovery_queue import diagnostics
    return diagnostics(db)


# Free-tier fallback: explicit single-item manual execution by the authenticated owner.
# It has no unattended loop, no outgoing messages, and never selects another job.
from threading import Lock
_manual_contact_step_lock = Lock()


@router.post('/discovery-jobs/{job_id}/process-one')
def manually_process_contact_job(job_id: int, db: Session = Depends(get_db)):
    from app.db.models import ContactDiscoveryJob
    from app.services.contact_discovery_queue import run_one, progress
    if db.get(ContactDiscoveryJob, job_id) is None:
        raise HTTPException(404, "Lote não encontrado.")
    if not _manual_contact_step_lock.acquire(blocking=False):
        raise HTTPException(429, "Uma pesquisa manual já está em andamento nesta instância.")
    try:
        try:
            attempted = run_one(db, job_id=job_id)
        except Exception:
            db.rollback()
            raise HTTPException(503, "Processamento manual indisponível; confira o histórico do lote.")
    finally:
        _manual_contact_step_lock.release()
    db.add(AuditLog(event="discovery_manual_step", entity_type="contact_discovery_job",
                    entity_id=job_id, details={"attempted":attempted}))
    db.commit()
    return {"attempted":attempted, "job":progress(db, job_id),
            "note":"No máximo uma empresa do lote por acionamento. Pesquisa apenas site cadastrado, "
                   "sem envio de mensagens. Novos contatos permanecem a verificar."}


@router.get('/export.csv')
def export_business_contacts(uf: str = Query('AM',pattern='^[A-Za-z]{2}$'),
                             city: str = Query('Manaus',min_length=1,max_length=100),
                             status: str = Query('verificado',pattern='^(verificado|a_verificar|todos)$'),
                             limit: int = Query(1000,ge=1,le=5000),
                             offset: int = Query(0,ge=0,le=100000),
                             db: Session = Depends(get_db)):
    """Explicit owner CSV download; protected by session; no extra credentials or API calls."""
    from fastapi import Response
    from app.services.contact_export import export_csv
    try:
        contents, n, has_more = export_csv(db,uf=uf,city=city,status=status,limit=limit,offset=offset)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    return Response(content=contents,media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition":"attachment; filename=leadcob-contatos-institucionais.csv",
                             "Cache-Control":"no-store","X-Exported-Rows":str(n),
                             "X-Has-More": "true" if has_more else "false",
                             "X-Next-Offset": str(offset+n) if has_more else ""})


@router.get("/contactability")
def institutional_contactability(uf: str = Query("AM", pattern="^[A-Za-z]{2}$"),
                                  city: str = Query("Manaus", min_length=1, max_length=100),
                                  db: Session = Depends(get_db)):
    """Owner-only aggregate, no CNPJ, company name or contact value in response."""
    from app.services.contact_readiness import contactability
    try:
        return contactability(db, uf, city)
    except ValueError as exc:
        raise HTTPException(422, "UF ou município inválidos.") from exc
