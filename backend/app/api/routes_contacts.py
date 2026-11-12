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
from app.db.models import BusinessContact, Company, Suppression, AuditLog

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
    return db.query(Suppression).filter(or_(Suppression.company_id == company.id, Suppression.cnpj == company.cnpj) if company.cnpj else Suppression.company_id == company.id).first() is not None

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

def insert(db, company, kind, value, source, url=None):
    if not value or is_blocked(db, company): return False
    v = clean(kind, value)
    existing = db.query(BusinessContact).filter_by(company_id=company.id, kind=kind, value=v).first()
    if existing: return False
    db.add(BusinessContact(company_id=company.id, kind=kind, value=v, source_name=source, source_url=url))
    return True

@router.get("")
def list_contacts(q: str = "", kind: str = "", company_id: int | None = None, status: str = "", uf: str = "", city: str = "", limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    query = db.query(BusinessContact, Company).join(Company, BusinessContact.company_id == Company.id)
    blocked_ids = [x.company_id for x in db.query(Suppression).filter(Suppression.company_id.isnot(None)).all()]
    blocked_cnpjs = [x.cnpj for x in db.query(Suppression).filter(Suppression.cnpj.isnot(None)).all()]
    if blocked_ids: query = query.filter(~Company.id.in_(blocked_ids))
    if blocked_cnpjs: query = query.filter(or_(Company.cnpj.is_(None), ~Company.cnpj.in_(blocked_cnpjs)))
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
            if insert(db, c, "email", item["email"], "Site institucional (leitura automática)", item["source_url"]): added += 1
        except HTTPException:
            pass
    for item in result.get("channels", []):
        try:
            if insert(db, c, item["kind"], item["value"], "Site institucional (leitura automática)", item["source_url"]):
                added += 1
        except HTTPException:
            pass
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
