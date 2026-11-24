"""Read-only corporate contactability metrics. Local data, not a market census."""
import re
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select, func
from app.db.models import Company, BusinessContact, Suppression
from app.services.cnpj import clean_cnpj, is_valid_cnpj
from app.collectors.site_contacts import _role_box, published_channels
from html import escape
from app.services.safe_http import validate_url

DIRECT = ("email", "phone", "whatsapp", "linkedin", "instagram", "facebook")


def _corporate(nature):
    text = str(nature or "").strip()
    return bool(text) and "individual" not in text.casefold() and not text.startswith(("213", "2.1.3"))


def _institutional_contact(kind, value):
    value = str(value or "").strip()
    if not value or value.casefold().startswith("anon:"):
        return False
    if kind == "email":
        return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) and _role_box(value.split("@", 1)[0]))
    if kind in ("phone", "whatsapp"):
        return bool(
            re.fullmatch(r"\+?[0-9() .-]+", value)
            and 10 <= len(re.sub(r"\D", "", value)) <= 13
        )
    if kind in ("linkedin", "instagram", "facebook"):
        try:
            validate_url(value)
            # This parser already guards against profile look-alike domains,
            # user-profile LinkedIn URLs and generic social-share links.
            matches = published_channels(
                f'<a href="{escape(value, quote=True)}">perfil institucional</a>',
                value,
            )
            return any(link["kind"] == kind for link in matches)
        except ValueError:
            return False
    return False


def _source_url(value):
    try:
        validate_url(str(value or ""))
        return True
    except ValueError:
        return False


def contactability(db, uf="AM", city="Manaus"):
    uf = uf.strip().upper()
    city = city.strip()
    if not re.fullmatch("[A-Z]{2}", uf) or not city or len(city) > 100:
        raise ValueError("UF e município inválidos.")
    blocked_ids = set(db.scalars(select(Suppression.company_id).where(
        Suppression.company_id.isnot(None))))
    blocked_cnpjs = {clean_cnpj(x) for x in db.scalars(select(Suppression.cnpj).where(
        Suppression.cnpj.isnot(None)))}
    if blocked_ids:
        blocked_cnpjs.update(clean_cnpj(x) for x in db.scalars(
            select(Company.cnpj).where(Company.id.in_(blocked_ids))) if x)

    scope = (func.upper(func.trim(Company.state)) == uf,
             func.lower(func.trim(Company.city)) == city.lower())
    groups = defaultdict(list)
    company_stream = db.execute(select(
        Company.id, Company.cnpj, Company.registration_status,
        Company.legal_nature, Company.website, Company.name).where(*scope)).yield_per(500)
    try:
        for id_, raw_cnpj, status, nature, site, name in company_stream:
            key = clean_cnpj(raw_cnpj)
            if id_ in blocked_ids or key in blocked_cnpjs or not is_valid_cnpj(key):
                continue
            groups[key].append((id_, str(status or "").strip().upper(), nature, site, name))
    finally:
        company_stream.close()

    active = 0
    corporate_ids = {}
    with_site = 0
    conflicting_sites = 0
    for cnpj, rows in groups.items():
        if not rows or any(x[1] != "ATIVA" for x in rows):
            continue
        active += 1
        companies = [x for x in rows if _corporate(x[2]) and
                     not re.search(r"[0-9]{11}\s*$", str(x[4] or ""))]
        if not companies:
            continue
        for x in companies:
            corporate_ids[x[0]] = cnpj
        sites = {str(x[3]).strip() for x in companies if x[3] and str(x[3]).strip()}
        if len(sites) == 1:
            with_site += 1
        elif len(sites) > 1:
            conflicting_sites += 1

    available = {k:set() for k in DIRECT}
    verified = {k:set() for k in DIRECT}
    sourced = {k:set() for k in DIRECT}
    verified_sourced = {k:set() for k in DIRECT}
    contact_stream = db.execute(select(
        BusinessContact.company_id, BusinessContact.kind, BusinessContact.status,
        BusinessContact.value, BusinessContact.source_url
    ).join(Company, BusinessContact.company_id == Company.id).where(
        *scope, BusinessContact.kind.in_(DIRECT),
        BusinessContact.status.in_(("a_verificar", "verificado"))
    )).yield_per(500)
    try:
        for id_, kind, status, value, source in contact_stream:
            cnpj = corporate_ids.get(id_)
            if cnpj is None or not _institutional_contact(kind, value):
                continue
            available[kind].add(cnpj)
            if status == "verificado":
                verified[kind].add(cnpj)
            if _source_url(source):
                sourced[kind].add(cnpj)
                if status == "verificado":
                    verified_sourced[kind].add(cnpj)
    finally:
        contact_stream.close()

    corporate = len(set(corporate_ids.values()))
    any_channel = set().union(*available.values())
    any_verified = set().union(*verified.values())
    any_verified_source = set().union(*verified_sourced.values())
    return {
        "uf": uf, "city":city, "observed_at":datetime.now(timezone.utc).isoformat(),
        "valid_unique_cnpjs": len(groups),
        "active_unique_cnpjs": active,
        "active_corporate_cnpjs":corporate,
        "with_consistent_registered_site":with_site,
        "with_conflicting_sites":conflicting_sites,
        "with_any_direct_channel":len(any_channel),
        "with_verified_direct_channel":len(any_verified),
        "with_verified_sourced_direct_channel":len(any_verified_source),
        "without_direct_channel":corporate-len(any_channel),
        "channels":{k:{"registered":len(available[k]), "verified":len(verified[k]),
                       "with_source_url":len(sourced[k]),
                       "verified_with_source_url":len(verified_sourced[k])} for k in DIRECT},
        "note":"Contagem de CNPJs distintos da base local; apenas canais institucionais válidos cadastrados. "
               "Verificado indica revisão interna, não confirma entrega, consentimento, base legal ou intenção de compra. "
               "Um CNPJ pode ter vários canais. Base não é censo oficial."
    }
