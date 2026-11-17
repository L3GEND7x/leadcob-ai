"""Local CNPJ inventory, not a census or a qualified lead count."""
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from app.db.models import Company, Suppression
from app.services.cnpj import clean_cnpj, is_valid_cnpj


def registry_coverage(db, uf="AM", city="Manaus"):
    blocked_ids = set(db.scalars(select(Suppression.company_id).where(Suppression.company_id.isnot(None))))
    blocked_cnpjs = {clean_cnpj(c) for c in db.scalars(select(Suppression.cnpj).where(Suppression.cnpj.isnot(None)))}
    blocked_cnpjs.update(clean_cnpj(c) for c in db.scalars(select(Company.cnpj).where(Company.id.in_(select(Suppression.company_id).where(Suppression.company_id.isnot(None))))) if c)
    observed = datetime.now(timezone.utc)
    query = select(Company.id, Company.cnpj, Company.registration_status, Company.registry_source,
                   Company.registry_updated_at, Company.target_profile).where(
        func.upper(func.trim(Company.state)) == uf.strip().upper(),
        func.lower(func.trim(Company.city)) == city.strip().lower())
    groups = defaultdict(list)
    missing = invalid = total = 0
    sources = Counter()
    for cid, cnpj, status, source, updated, profile in db.execute(query):
        if cid in blocked_ids or (cnpj and clean_cnpj(cnpj) in blocked_cnpjs):
            continue
        total += 1
        if not cnpj or not cnpj.strip():
            missing += 1
            continue
        if not is_valid_cnpj(cnpj):
            invalid += 1
            continue
        groups[clean_cnpj(cnpj)].append((status, source, updated, profile))
        sources[source or "Não informada"] += 1
    active = inactive = unknown = conflict = evidenced = profiled = 0
    freshness = Counter()
    for rows in groups.values():
        dates = [x[2].replace(tzinfo=timezone.utc) if x[2].tzinfo is None else x[2] for x in rows if x[1] and x[1].strip() and x[2]]
        if not dates:
            freshness['missing'] += 1
        elif any(d > observed for d in dates):
            freshness['future_date'] += 1
        elif max(dates) >= observed - timedelta(days=90):
            freshness['within_90_days'] += 1
        else:
            freshness['older_than_90_days'] += 1
        statuses = {str(row[0] or "").strip().upper() for row in rows} - {""}
        if len(statuses) > 1:
            conflict += 1
        elif statuses == {"ATIVA"}:
            active += 1
        elif statuses and statuses <= {"NULA","SUSPENSA","INAPTA","BAIXADA"}:
            inactive += 1
        else:
            unknown += 1
        evidenced += int(any(row[1] and row[2] for row in rows))
        profiled += int(any(row[3] for row in rows))
    valid = total - missing - invalid
    return dict(uf=uf.strip().upper(), city=city.strip(), observed_at=observed.isoformat(),
                company_records=total, missing_cnpj_records=missing, invalid_cnpj_records=invalid,
                valid_cnpj_records=valid, unique_valid_cnpjs=len(groups), duplicate_valid_records=valid-len(groups),
                active_cnpjs=active, inactive_cnpjs=inactive, unknown_status_cnpjs=unknown,
                conflicting_status_cnpjs=conflict, with_registry_source_and_date=evidenced,
                with_target_profile=profiled, sources_by_valid_record=dict(sources),
                registry_update_age={k:freshness[k] for k in ('missing','future_date','within_90_days','older_than_90_days')},
                market_total=None, market_coverage_pct=None,
                note="Base local não suprimida; CNPJ válido não comprova atividade atual, demanda ou contato. Sem denominador oficial comparável.")
