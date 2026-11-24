"""Private owner CSV export of institutional contacts with post-validation pagination.

Do not export people or suppression records. Each request is read-only.
"""
import csv
import io
import re

from sqlalchemy import select, func, case
from app.db.models import Company, BusinessContact, Suppression
from app.services.cnpj import clean_cnpj, is_valid_cnpj
from app.collectors.site_contacts import _role_box

CHANNELS = {"email", "phone", "whatsapp", "linkedin", "instagram", "facebook", "website"}
STATUS = {"verificado", "a_verificar", "todos"}
HEADERS = ("CNPJ", "Razão social", "UF", "Município", "Canal", "Contato institucional",
           "Situação do contato", "Fonte", "URL de origem", "Data da conferência")


def safe_cell(value):
    """Block CSV formulas and control characters without corrupting numeric fields."""
    value = str(value or "").replace("\r", " ").replace("\n", " ").replace("\x00", " ").strip()
    if value.startswith(("=", "+", "-", "@")):
        value = "'" + value
    return value[:2000]


def export_csv(db, *, uf="AM", city="Manaus", status="verificado", limit=1000, offset=0):
    if len(uf) != 2 or not uf.isascii() or not uf.isalpha():
        raise ValueError("UF inválida")
    if not city.strip() or len(city) > 100 or status not in STATUS:
        raise ValueError("Filtros inválidos")
    if not 1 <= limit <= 5000 or not 0 <= offset <= 100000:
        raise ValueError("Paginação inválida")

    # Suppression of any duplicate establishment blocks the normalized CNPJ.
    blocked_ids = set(db.scalars(select(Suppression.company_id).where(
        Suppression.company_id.isnot(None))))
    blocked_cnpjs = {clean_cnpj(c) for c in db.scalars(select(Suppression.cnpj).where(
        Suppression.cnpj.isnot(None)))}
    if blocked_ids:
        blocked_cnpjs.update(clean_cnpj(c) for c in db.scalars(
            select(Company.cnpj).where(Company.id.in_(blocked_ids))) if c)

    query = (
        select(Company, BusinessContact)
        .join(BusinessContact, BusinessContact.company_id == Company.id)
        .where(
            func.upper(func.trim(Company.state)) == uf.upper(),
            func.lower(func.trim(Company.city)) == city.strip().lower(),
            func.upper(func.trim(Company.registration_status)) == "ATIVA",
            BusinessContact.kind.in_(CHANNELS),
            BusinessContact.status.in_(
                ("verificado", "a_verificar") if status == "todos" else (status,)),
        )
        # Deterministic ordering makes pagination reproducible on an unchanged database.
        # For a duplicated contact, prefer the verified record with source provenance.
        .order_by(
            Company.cnpj, BusinessContact.kind,
            func.lower(func.trim(BusinessContact.value)),
            case((BusinessContact.status == "verificado", 0), else_=1),
            BusinessContact.id, Company.id,
        )
    )

    stream = db.execute(query).yield_per(250)
    data = io.StringIO(newline="")
    data.write("\ufeff")
    writer = csv.writer(data, delimiter=";", lineterminator="\r\n")
    writer.writerow(HEADERS)
    seen = set()
    eligible = 0
    emitted = 0
    has_more = False
    try:
        for company, contact in stream:
            cnpj = clean_cnpj(company.cnpj)
            if not is_valid_cnpj(cnpj) or company.id in blocked_ids or cnpj in blocked_cnpjs:
                continue
            nature = str(company.legal_nature or "").strip()
            if not nature or "individual" in nature.casefold() or nature.startswith(("213", "2.1.3")):
                continue
            if re.search(r"[0-9]{11}\s*$", company.name or ""):
                continue
            value = (contact.value or "").strip()
            if not value or value.casefold().startswith("anon:"):
                continue
            if contact.status != "verificado" and not contact.source_url:
                continue
            if contact.kind == "email" and not _role_box(value.split("@", 1)[0]):
                continue
            key = (cnpj, contact.kind, value.casefold())
            if key in seen:
                continue
            seen.add(key)
            if eligible < offset:
                eligible += 1
                continue
            if emitted >= limit:
                has_more = True
                break
            eligible += 1
            writer.writerow(tuple(safe_cell(v) for v in (
                cnpj, company.name, company.state, company.city, contact.kind, value,
                contact.status, contact.source_name, contact.source_url,
                contact.checked_at.isoformat() if contact.checked_at else "",
            )))
            emitted += 1
    finally:
        stream.close()
    return data.getvalue().encode("utf-8"), emitted, has_more
