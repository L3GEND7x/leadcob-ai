"""Explicit opt-in public registry projection; never expose owner CRM or contact values."""
from collections import defaultdict
from datetime import datetime, timezone
import re
from sqlalchemy import select, func
from fastapi import HTTPException
from app.core.config import settings
from app.core.account_access import authorize
from app.db.models import Company, Suppression, WorkspaceContact, WorkspaceSuppression
from app.services.commercial_entitlements import check_subscription
from app.services.cnpj import clean_cnpj, is_valid_cnpj
from app.services.segments import SEGMENTS, profile_for
from app.core.security import stamp

KINDS={"email","phone","whatsapp","linkedin","instagram","facebook","website"}
# Only explicit public RFB import provenance, not arbitrary external/manual records.
RFB_SOURCE=re.compile(r"^Receita Federal — (?:dados abertos [0-9]{4}-[0-9]{2}(?: \(arquivos locais\))?|snapshot AM [0-9]{4}-[0-9]{2}-[0-9]{2})$")
CPF_TAIL=re.compile(r"\d{11}\s*$")
MAX_SCAN=100000

def options(db,token,organization_id):
    authorize(db,token,organization_id,"read")
    check_subscription(db,organization_id)
    return {"enabled":settings.workspace_registry_search_enabled,
        "segments":[{"key":k,"label":v["label"]} for k,v in SEGMENTS.items()],
        "channels":sorted(KINDS)}

def search(db,token,organization_id,uf,city,segment=None,channel=None,limit=30,offset=0):
    principal=authorize(db,token,organization_id,"read")
    check_subscription(db,principal.organization_id)
    if not settings.workspace_registry_search_enabled:
        raise HTTPException(503,"Pesquisa regional ainda não habilitada.")
    if not city.strip() or not re.fullmatch(r"[A-Za-z]{2}",uf) or (segment and segment not in SEGMENTS) or (channel and channel not in KINDS):
        raise HTTPException(422,"Filtros inválidos.")
    if not 1<=limit<=50 or not 0<=offset<=5000:
        raise HTTPException(422,"Paginação inválida.")
    scope=principal.organization_id
    blocked={clean_cnpj(x) for x in db.scalars(select(WorkspaceSuppression.cnpj).where(WorkspaceSuppression.organization_id==scope))}
    blocked.update(clean_cnpj(x) for x in db.scalars(select(Suppression.cnpj).where(Suppression.cnpj.isnot(None))))
    blocked.update(clean_cnpj(x) for x in db.scalars(select(Company.cnpj).join(Suppression,Suppression.company_id==Company.id)))
    candidates=defaultdict(list)
    query=select(Company.cnpj,Company.name,Company.state,Company.city,Company.cnae_main,
        Company.legal_nature,Company.registration_status,Company.registry_source,Company.registry_updated_at).where(
        func.upper(func.trim(Company.state))==uf.strip().upper(),
        func.lower(func.trim(Company.city))==city.strip().lower()).limit(MAX_SCAN+1)
    for count,row in enumerate(db.execute(query),1):
        if count>MAX_SCAN:
            raise HTTPException(422,"Município excede o limite experimental de pesquisa.")
        key=clean_cnpj(row.cnpj)
        if key not in blocked and is_valid_cnpj(key):
            candidates[key].append(row)
    private_channels=defaultdict(set)
    for key,kind in db.execute(select(WorkspaceContact.cnpj,WorkspaceContact.kind).where(
        WorkspaceContact.organization_id==scope,WorkspaceContact.kind.in_(KINDS)).distinct()):
        private_channels[clean_cnpj(key)].add(kind)
    items=[]
    for key,rows in candidates.items():
        # Conflicting duplicate records or unclear identity are excluded, not merged.
        if any(not x.registry_source or not RFB_SOURCE.fullmatch(x.registry_source)
               or not x.registry_updated_at or not x.name or CPF_TAIL.search(x.name)
               or not x.legal_nature or "individual" in x.legal_nature.casefold()
               or x.legal_nature.startswith(("213","2.1.3"))
               or str(x.registration_status or "").strip().upper()!="ATIVA"
               for x in rows):
            continue
        signatures={(x.name,x.cnae_main,x.legal_nature) for x in rows}
        if len(signatures)!=1:
            continue
        row=max(rows,key=lambda x:stamp(x.registry_updated_at))
        profile=profile_for(row.cnae_main)
        if profile is None or (segment and segment!=profile):
            continue
        kinds=private_channels.get(key,set())
        if channel and channel not in kinds:
            continue
        items.append(dict(cnpj=key,razao_social=row.name,municipio=row.city,uf=row.state,
            cnae_principal=row.cnae_main,segment=profile,segment_label=SEGMENTS[profile]["label"],
            source=row.registry_source,registry_updated_at=stamp(row.registry_updated_at).isoformat(),
            private_channels=sorted(kinds)))
    items.sort(key=lambda x:(not bool(x["private_channels"]),x["razao_social"].casefold(),x["cnpj"]))
    return {"total":len(items),"items":items[offset:offset+limit],
        "observed_at":datetime.now(timezone.utc).isoformat(),
        "note":"Base cadastral local parcial, sem confirmação de demanda. Canais são apenas os cadastrados pela sua organização; não são contatos verificados."}
