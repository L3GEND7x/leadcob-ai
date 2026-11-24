"""Prioritization, not a prediction of debt or hiring intent."""
import re
from collections import Counter, defaultdict
from heapq import nsmallest
from functools import lru_cache
from datetime import datetime, timezone
from sqlalchemy import select, func
from app.db.models import Company, Opportunity, BusinessContact, Suppression
from app.services.cnpj import clean_cnpj, is_valid_cnpj
from app.services.segments import profile_for, SEGMENTS
from app.services.contact_readiness import DIRECT, _institutional_contact, _corporate, _source_url

DIRECT_CHANNELS = set(DIRECT)


def tier(registry_active, sourced, profile, evidence, channels, verified):
    if not registry_active or not sourced or profile is None:
        return "registry_review"
    if profile in {"concorrente_cobranca", "setor_publico"}:
        return "special_route"
    if evidence and verified:
        return "priority_review"
    if evidence:
        return "evidence_contact_needed"
    if channels:
        return "contactable_prospect"
    return "prospect_research"


def qualification(db, uf, city, limit=50, offset=0, selected_tier=None):
    blocked_ids = set(db.scalars(select(Suppression.company_id).where(Suppression.company_id.isnot(None))))
    blocked_cnpjs = {clean_cnpj(c) for c in db.scalars(select(Suppression.cnpj).where(Suppression.cnpj.isnot(None)))}
    # Suppressing one duplicate also suppresses the establishment represented by it.
    if blocked_ids:
        blocked_cnpjs.update(clean_cnpj(c) for c in db.scalars(select(Company.cnpj).where(
            Company.id.in_(select(Suppression.company_id).where(Suppression.company_id.isnot(None))))) if c)
    city_filter = (func.upper(func.trim(Company.state)) == uf.strip().upper(),
                   func.lower(func.trim(Company.city)) == city.strip().lower())
    groups = defaultdict(list)
    eligible_ids = set()
    cached_profile = lru_cache(maxsize=4096)(profile_for)
    for row in db.execute(select(Company.id,Company.cnpj,Company.name,Company.registration_status,
        Company.registry_source,Company.registry_updated_at,Company.cnae_main,Company.legal_nature).where(*city_filter)):
        key = clean_cnpj(row.cnpj)
        if row.id not in blocked_ids and key not in blocked_cnpjs and is_valid_cnpj(key):
            groups[key].append(row)
            eligible_ids.add(row.id)
    contacts = defaultdict(set)
    verified = defaultdict(set)
    for cid,kind,status,value in db.execute(select(BusinessContact.company_id,BusinessContact.kind,
        BusinessContact.status,BusinessContact.value).join(Company,Company.id==BusinessContact.company_id)
        .where(*city_filter,BusinessContact.status.in_(["verificado","a_verificar"]),
        BusinessContact.kind.in_(DIRECT_CHANNELS),
        BusinessContact.value.isnot(None)).distinct()):
        if cid in eligible_ids and _institutional_contact(kind, value):
            contacts[cid].add(kind)
            if status=="verificado":
                verified[cid].add(kind)
    evidence = defaultdict(list)
    for oid,cid,kind,source_url,source_name in db.execute(select(Opportunity.id,Opportunity.company_id,Opportunity.kind,
        Opportunity.source_url,Opportunity.source_name)
        .join(Company,Company.id==Opportunity.company_id).where(*city_filter,
        Opportunity.status=="qualified", Opportunity.is_verified.is_(True),
        Opportunity.source_url.isnot(None), Opportunity.source_url!="",
        Opportunity.source_name!="Demonstração", Opportunity.kind.in_(["hiring","outsourcing","public_procurement"]))):
        if (cid in eligible_ids and _source_url(source_url)
                and str(source_name or '').strip()
                and str(source_name).strip().casefold() != 'demonstração'):
            evidence[cid].append((oid,kind))
    counts = Counter()
    channel_counts = {k: {'available': 0, 'verified': 0} for k in sorted(DIRECT_CHANNELS)}
    any_channel = any_verified = active_sourced = 0
    order={k:i for i,k in enumerate(('priority_review','evidence_contact_needed','contactable_prospect',
        'prospect_research','registry_review','special_route'))}
    total = 0
    def candidates():
        nonlocal total, any_channel, any_verified, active_sourced
        for cnpj,rows in groups.items():
            rows.sort(key=lambda x:x.id)
            r=rows[0]
            profiles={cached_profile(x.cnae_main) for x in rows}
            profile=next(iter(profiles)) if len(profiles)==1 else None
            active=all(str(x.registration_status or "").strip().upper()=="ATIVA" for x in rows)
            sourced=all(str(x.registry_source or '').strip() and x.registry_updated_at for x in rows)
            corporate=all(_corporate(x.legal_nature) and
                          not re.search(r"[0-9]{11}\s*$", str(x.name or "")) for x in rows)
            # Do not combine inconsistent duplicates into a qualified prospect.
            ids=[x.id for x in rows]
            ch=set().union(*(contacts.get(i, ()) for i in ids))
            v=set().union(*(verified.get(i, ()) for i in ids))
            ev=[e for i in ids for e in evidence.get(i, ())]
            if not corporate:
                ch, v, ev = set(), set(), []
            category=tier(active and corporate,sourced,profile,ev,ch,v)
            counts[category]+=1
            if active and sourced and corporate:
                active_sourced += 1
                any_channel += int(bool(ch))
                any_verified += int(bool(v))
                for k in ch:
                    channel_counts[k]['available'] += 1
                for k in v:
                    channel_counts[k]['verified'] += 1
            if selected_tier and selected_tier!=category:
                continue
            total += 1
            yield dict(company_id=r.id,cnpj=cnpj,name=r.name if corporate else 'Cadastro empresarial a revisar',profile=profile,
                profile_label=SEGMENTS.get(profile,{}).get("label"),tier=category,
                channels=sorted(ch),verified_channels=sorted(v),
                evidence_ids=sorted({e[0] for e in ev}),evidence_kinds=sorted({e[1] for e in ev}))
    items = nsmallest(offset+limit, candidates(), key=lambda x:(order[x["tier"]],-len(x["verified_channels"]),x["company_id"]))
    return dict(uf=uf,city=city,observed_at=datetime.now(timezone.utc).isoformat(),counts=dict(counts),
        unique_cnpjs=len(groups),total=total,items=items[offset:offset+limit],
        contact_coverage=dict(active_sourced_cnpjs=active_sourced, with_any_channel=any_channel,
          with_verified_channel=any_verified, without_any_channel=active_sourced-any_channel,
          channels=channel_counts),
        note="Prioridade de revisão, não confirmação de demanda, dívida ou intenção de contratar. Natureza jurídica ausente ou individual requer revisão; evidências exigem URL HTTP(S) formalmente válida. Canais passam por validação formal, não por teste de entrega. Evidências qualificadas já registradas podem estar desatualizadas.")
