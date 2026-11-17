"""Local CNPJ inventory, not a census or a qualified lead count."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from sqlalchemy import select, func
from app.db.models import Company, Suppression
from app.services.cnpj import clean_cnpj, is_valid_cnpj


def registry_coverage(db, uf="AM", city="Manaus"):
    blocked_ids = select(Suppression.company_id).where(Suppression.company_id.isnot(None))
    blocked_cnpjs = select(Suppression.cnpj).where(Suppression.cnpj.isnot(None))
    query = select(Company.cnpj, Company.registration_status, Company.registry_source,
                   Company.registry_updated_at, Company.target_profile).where(
        func.upper(func.trim(Company.state)) == uf.strip().upper(),
        func.lower(func.trim(Company.city)) == city.strip().lower(),
        ~Company.id.in_(blocked_ids),
        Company.cnpj.is_(None) | ~Company.cnpj.in_(blocked_cnpjs))
    groups = defaultdict(list)
    missing = invalid = total = 0
    sources = Counter()
    for cnpj, status, source, updated, profile in db.execute(query):
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
    for rows in groups.values():
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
    return dict(uf=uf.strip().upper(), city=city.strip(), observed_at=datetime.now(timezone.utc).isoformat(),
                company_records=total, missing_cnpj_records=missing, invalid_cnpj_records=invalid,
                valid_cnpj_records=valid, unique_valid_cnpjs=len(groups), duplicate_valid_records=valid-len(groups),
                active_cnpjs=active, inactive_cnpjs=inactive, unknown_status_cnpjs=unknown,
                conflicting_status_cnpjs=conflict, with_registry_source_and_date=evidenced,
                with_target_profile=profiled, sources_by_valid_record=dict(sources),
                market_total=None, market_coverage_pct=None,
                note="Base local não suprimida; CNPJ válido não comprova atividade atual, demanda ou contato. Sem denominador oficial comparável.")
