"""Read-only discovery targets aligned with the owner contactability report.

No third-party request, contact guessing, or automatic queue creation. Only
institutional company CNPJs eligible under the same rules as the dashboard
are offered for manual review.
"""
import re
from collections import defaultdict

from sqlalchemy import select, func
from app.db.models import Company, BusinessContact
from app.services.cnpj import clean_cnpj, is_valid_cnpj
from app.services.contact_readiness import (
    _corporate, _institutional_contact, _source_url,
)
from app.services.contact_suppression import suppression_keys

KINDS = {"email", "phone", "whatsapp", "linkedin", "instagram",
         "facebook", "website"}


def _channel_is_eligible(kind, value):
    if kind == "website":
        return _source_url(value)
    return _institutional_contact(kind, value)


def targets(db, uf, city, kind, limit=50, offset=0):
    if kind not in KINDS:
        raise ValueError("Canal inválido.")
    uf, city = str(uf).strip().upper(), str(city).strip()
    if not re.fullmatch(r"[A-Z]{2}", uf) or not city or len(city) > 100:
        raise ValueError("UF ou município inválido.")
    if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
        raise ValueError("Paginação inválida.")

    blocked_ids, blocked_keys = suppression_keys(db)
    scope = (
        func.upper(func.trim(Company.state)) == uf,
        func.lower(func.trim(Company.city)) == city.lower(),
    )

    # Keep all same-CNPJ rows in the location so a conflict can quarantine
    # the whole CNPJ instead of allowing its apparently active duplicate.
    groups = defaultdict(list)
    stream = db.execute(select(
        Company.id, Company.cnpj, Company.name, Company.website,
        Company.registration_status, Company.legal_nature,
    ).where(*scope)).yield_per(500)
    try:
        for row in stream:
            key = clean_cnpj(row.cnpj)
            if row.id in blocked_ids or key in blocked_keys or not is_valid_cnpj(key):
                continue
            groups[key].append(row)
    finally:
        stream.close()

    active = 0
    corporate = {}
    corporate_groups = {}
    for key, rows in groups.items():
        if any(str(row.registration_status or "").strip().upper() != "ATIVA"
               for row in rows):
            continue
        active += 1
        eligible = [
            row for row in rows
            if _corporate(row.legal_nature)
            and not re.search(r"[0-9]{11}\s*$", str(row.name or ""))
        ]
        if not eligible:
            continue
        corporate_groups[key] = eligible
        for row in eligible:
            corporate[row.id] = key

    present, verified, sourced_verified = set(), set(), set()
    contact_stream = db.execute(select(
        BusinessContact.company_id, BusinessContact.status,
        BusinessContact.value, BusinessContact.source_url,
    ).join(Company, Company.id == BusinessContact.company_id).where(
        *scope, BusinessContact.kind == kind,
        BusinessContact.status.in_(("a_verificar", "verificado")),
    )).yield_per(500)
    try:
        for company_id, status, value, source_url in contact_stream:
            key = corporate.get(company_id)
            if key is None or not _channel_is_eligible(kind, value):
                continue
            present.add(key)
            if status == "verificado":
                verified.add(key)
                if _source_url(source_url):
                    sourced_verified.add(key)
    finally:
        contact_stream.close()

    items = []
    for key, rows in corporate_groups.items():
        if key in present:
            continue
        # A site becomes a *candidate* for a manually confirmed fetch only
        # if all eligible local rows agree and the URL shape is valid.
        sites = {str(row.website).strip() for row in rows
                 if row.website and str(row.website).strip()}
        valid_sites = {site for site in sites if _source_url(site)}
        ready = len(sites) == 1 and len(valid_sites) == 1
        candidates = [row for row in rows
                      if row.website and str(row.website).strip() in valid_sites]
        row = min(candidates if ready else rows, key=lambda item: item.id)
        reason = (
            "registered_site" if ready else
            "conflicting_sites" if len(sites) > 1 else
            "invalid_site" if sites else "missing_site"
        )
        items.append({
            "company_id": row.id,
            "cnpj": key,
            "name": row.name,
            "discovery_ready": ready,
            "reason": reason,
        })
    items.sort(key=lambda item: (not item["discovery_ready"], item["company_id"]))
    return {
        "uf": uf, "city": city, "kind": kind,
        "active_unique_cnpjs": active,
        "active_corporate_cnpjs": len(corporate_groups),
        "with_channel": len(present),
        "with_verified_channel": len(verified),
        "with_verified_sourced_channel": len(sourced_verified),
        "missing_channel": len(items),
        "ready_for_site_discovery": sum(item["discovery_ready"] for item in items),
        "items": items[offset:offset + limit],
        "note": (
            "Apenas CNPJs empresariais ativos, não suprimidos, com status consistente "
            "e canais institucionais válidos na base local. Ausência de registro não "
            "comprova ausência do canal. Site exige revisão de titularidade; nenhuma "
            "coleta ocorre nesta consulta."
        ),
    }
