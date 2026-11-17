"""Read-only discovery targets; no external search, messaging or inferred contacts."""
from collections import defaultdict
from sqlalchemy import select, func
from app.db.models import Company, BusinessContact, Suppression
from app.services.cnpj import clean_cnpj, is_valid_cnpj

KINDS = {"email","phone","whatsapp","linkedin","instagram","facebook","website"}


def targets(db, uf, city, kind, limit=50, offset=0):
    if kind not in KINDS:
        raise ValueError("Canal inválido.")
    blocked_ids = set(db.scalars(select(Suppression.company_id).where(Suppression.company_id.isnot(None))))
    blocked_keys = {clean_cnpj(c) for c in db.scalars(select(Suppression.cnpj).where(Suppression.cnpj.isnot(None)))}
    blocked_keys.update(clean_cnpj(c) for c in db.scalars(select(Company.cnpj).where(
        Company.id.in_(select(Suppression.company_id).where(Suppression.company_id.isnot(None))))) if c)
    scope = (func.upper(func.trim(Company.state)) == uf.strip().upper(),
             func.lower(func.trim(Company.city)) == city.strip().lower())
    groups = defaultdict(list)
    for row in db.execute(select(Company.id,Company.cnpj,Company.name,Company.website,
        Company.registration_status).where(*scope)):
        key = clean_cnpj(row.cnpj)
        if row.id not in blocked_ids and key not in blocked_keys and is_valid_cnpj(key):
            groups[key].append(row)
    present, verified = set(), set()
    for cid,status,value in db.execute(select(BusinessContact.company_id,BusinessContact.status,
        BusinessContact.value).join(Company,Company.id==BusinessContact.company_id).where(
        *scope,BusinessContact.kind==kind,BusinessContact.status.in_(["a_verificar","verificado"]))):
        if value and value.strip() and not value.strip().lower().startswith("anon:"):
            present.add(cid)
            if status == "verificado":
                verified.add(cid)
    items=[]
    active=available=checked=0
    for key,rows in groups.items():
        if not all(str(x.registration_status or "").strip().upper()=="ATIVA" for x in rows):
            continue
        active += 1
        ids={x.id for x in rows}
        available += int(bool(ids & present))
        checked += int(bool(ids & verified))
        if ids & present:
            continue
        # Avoid choosing a website when duplicate records disagree.
        sites={x.website.strip() for x in rows if x.website and x.website.strip()}
        candidates=sorted((x for x in rows if x.website and x.website.strip()),key=lambda x:x.id)
        ready=len(sites)==1 and bool(candidates)
        row=candidates[0] if ready else min(rows,key=lambda x:x.id)
        items.append(dict(company_id=row.id,cnpj=key,name=row.name,
                          discovery_ready=ready,reason="registered_site" if ready else
                          ("conflicting_sites" if len(sites)>1 else "missing_site")))
    items.sort(key=lambda x:(not x["discovery_ready"],x["company_id"]))
    return dict(uf=uf,city=city,kind=kind,active_unique_cnpjs=active,with_channel=available,
        with_verified_channel=checked,missing_channel=len(items),
        ready_for_site_discovery=sum(x["discovery_ready"] for x in items),
        items=items[offset:offset+limit],note="Ausência no diretório não comprova ausência externa. Site cadastrado exige revisão de titularidade; coleta depende do worker.")
