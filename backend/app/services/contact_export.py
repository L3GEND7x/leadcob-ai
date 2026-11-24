"""Owner-only institutional contact export; no writes or external network access."""
import csv
import io
from datetime import datetime, timezone

from sqlalchemy import select, func
from app.db.models import Company, BusinessContact, Suppression
from app.services.cnpj import clean_cnpj, is_valid_cnpj
from app.collectors.site_contacts import _role_box

CHANNELS={"email","phone","whatsapp","linkedin","instagram","facebook","website"}
STATUS={"verificado","a_verificar","todos"}
HEADERS=("CNPJ","Razão social","UF","Município","Canal","Contato institucional",
         "Situação do contato","Fonte","URL de origem","Data da conferência")


def safe_cell(value):
    """Prevent spreadsheet-formula execution and one-cell-to-many-row injection."""
    value=str(value or "").replace("\r"," ").replace("\n"," ").replace("\x00"," ").strip()
    if value.lstrip().startswith(("=","+","-","@")):
        return "'"+value
    return value[:2000]


def export_csv(db, *, uf="AM", city="Manaus", status="verificado",
               limit=1000, offset=0):
    if len(uf)!=2 or not uf.isascii() or not uf.isalpha():
        raise ValueError("UF inválida")
    if not city.strip() or len(city)>100 or status not in STATUS:
        raise ValueError("Filtros inválidos")
    if not 1<=limit<=5000 or not 0<=offset<=100000:
        raise ValueError("Paginação inválida")
    scope=(func.upper(func.trim(Company.state))==uf.upper(),
           func.lower(func.trim(Company.city))==city.strip().lower(),
           func.upper(func.trim(Company.registration_status))=="ATIVA",
           BusinessContact.kind.in_(CHANNELS),
           BusinessContact.status.in_(("verificado","a_verificar") if status=="todos" else (status,)))
    # Suppressing one duplicate establishment suppresses the same CNPJ across records.
    blocked_ids=set(db.scalars(select(Suppression.company_id).where(
        Suppression.company_id.isnot(None))))
    blocked_keys={clean_cnpj(c) for c in db.scalars(select(Suppression.cnpj).where(
        Suppression.cnpj.isnot(None)))}
    if blocked_ids:
        blocked_keys.update(clean_cnpj(x) for x in db.scalars(
            select(Company.cnpj).where(Company.id.in_(blocked_ids))) if x)
    rows=db.execute(select(Company,BusinessContact).join(
        BusinessContact,BusinessContact.company_id==Company.id).where(
        *scope).order_by(Company.cnpj,BusinessContact.kind,BusinessContact.id).offset(offset).limit(limit))
    out=io.StringIO(newline="")
    out.write("\ufeff")
    writer=csv.writer(out,delimiter=";",quoting=csv.QUOTE_MINIMAL,lineterminator="\r\n")
    writer.writerow(HEADERS)
    emitted=0
    seen=set()
    for company, contact in rows:
        cnpj=clean_cnpj(company.cnpj)
        if not is_valid_cnpj(cnpj) or company.id in blocked_ids or cnpj in blocked_keys:
            continue
        value=(contact.value or "").strip()
        if not value or value.casefold().startswith("anon:"):
            continue
        if contact.status!="verificado" and not contact.source_url:
            continue
        if contact.kind=="email" and not _role_box(value.split("@",1)[0]):
            continue
        # Only contacts marked as institutional in the directory, never names of personnel.
        key=(cnpj, contact.kind, value.casefold())
        if key in seen:
            continue
        seen.add(key)
        writer.writerow(tuple(safe_cell(v) for v in (
            cnpj, company.name, company.state, company.city, contact.kind,
            value, contact.status, contact.source_name, contact.source_url,
            contact.checked_at.isoformat() if contact.checked_at else "")))
        emitted+=1
    return out.getvalue().encode("utf-8"),emitted
