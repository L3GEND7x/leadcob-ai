"""Mapa de contato institucional e contactabilidade.

A pontuação mede apenas cobertura de canais institucionais disponíveis/verificados.
Não mede probabilidade de fechamento, inadimplência ou qualidade do lead.
"""
from __future__ import annotations

import re
from urllib.parse import urlencode, urlparse

CHANNEL_WEIGHTS = {
    "email": 25,
    "phone": 25,
    "whatsapp": 20,
    "linkedin": 10,
    "website": 10,
    "instagram": 5,
    "facebook": 5,
}
STATUS_FACTOR = {"verificado": 1.0, "a_verificar": 0.6, "invalido": 0.0}

DEPARTMENT_ALIASES = {
    "licitacao": "Licitações/Compras", "licitacoes": "Licitações/Compras", "compras": "Licitações/Compras",
    "financeiro": "Financeiro", "financeira": "Financeiro", "financas": "Finanças",
    "cobranca": "Cobrança/Crédito", "credito": "Cobrança/Crédito",
    "contasareceber": "Contas a Receber", "receber": "Contas a Receber",
    "faturamento": "Faturamento", "administrativo": "Administração", "administracao": "Administração",
    "juridico": "Jurídico", "comercial": "Comercial",
}


def department_from_email(value: str | None) -> str:
    local = (value or "").split("@", 1)[0].casefold()
    key = re.sub(r"[^a-z]", "", local)
    return DEPARTMENT_ALIASES.get(key, "geral")


def recommended_departments(company, opportunities) -> list[str]:
    active = [o for o in (opportunities or []) if getattr(o, "status", None) != "discarded"]
    public = any(getattr(o, "kind", None) == "public_procurement" for o in active)
    text = " ".join(
        f"{getattr(o, 'title', '')} {getattr(o, 'description', '')} {getattr(o, 'evidence', '')}"
        for o in active
    ).casefold()
    finance_hint = any(x in text for x in ("cobran", "crédit", "credito", "receb", "tribut", "finance"))
    if public:
        ordered = ["Finanças", "Licitações/Compras", "Administração"] if finance_hint else ["Licitações/Compras", "Finanças", "Administração"]
    else:
        ordered = ["Cobrança/Crédito", "Financeiro", "Contas a Receber", "Controladoria"]
    return ordered


def roles_to_find(company, opportunities) -> list[str]:
    if any(getattr(o, "kind", None) == "public_procurement" and getattr(o, "status", None) != "discarded"
           for o in (opportunities or [])):
        return ["responsável por Licitações/Compras", "responsável pela área de Finanças", "responsável administrativo"]
    return ["responsável por Cobrança/Crédito", "responsável Financeiro", "responsável por Contas a Receber/Controladoria"]


def _search_url(company, roles: list[str]) -> str:
    name = re.sub(r"^MUNIC[IÍ]PIO\s+DE\s+", "Prefeitura de ", company.name, flags=re.I)
    public = name.startswith("Prefeitura de ") or any("Licitações" in r for r in roles)
    location = " ".join(filter(None, [getattr(company, "city", None), getattr(company, "state", None)]))
    query = f'{name} {location} ' + ("licitações financeiro contato site:gov.br" if public else "financeiro cobrança contato site oficial")
    if getattr(company, "website", None):
        host = urlparse(company.website).hostname
        if host:
            query += f" site:{host}"
    return "https://duckduckgo.com/?" + urlencode({"q": query})


def build_map(company, contacts, opportunities=None) -> dict:
    valid = [c for c in contacts if getattr(c, "status", None) in {"verificado", "a_verificar"} and not c.value.startswith("anon:")]
    best_by_kind = {}
    for c in valid:
        factor = STATUS_FACTOR.get(getattr(c, "status", "a_verificar"), 0.6)
        current = best_by_kind.get(c.kind)
        if current is None or factor > current[0]:
            best_by_kind[c.kind] = (factor, c)

    score = 0
    for kind, (factor, _) in best_by_kind.items():
        score += round(CHANNEL_WEIGHTS.get(kind, 0) * factor)
    score = max(0, min(100, score))
    label = "Alta" if score >= 70 else "Média" if score >= 40 else "Baixa"

    priority = sorted(
        valid,
        key=lambda c: (
            STATUS_FACTOR.get(getattr(c, "status", "a_verificar"), 0.6),
            CHANNEL_WEIGHTS.get(getattr(c, "kind", ""), 0),
        ),
        reverse=True,
    )
    channels = []
    for c in priority:
        channels.append({
            "id": c.id,
            "kind": c.kind,
            "value": c.value,
            "status": c.status,
            "department": c.department,
            "source_name": c.source_name,
            "source_url": c.source_url,
        })

    departments = recommended_departments(company, opportunities or [])
    discovered_departments = []
    for c in valid:
        dep = (getattr(c, "department", None) or "geral").strip()
        if dep != "geral" and dep not in discovered_departments:
            discovered_departments.append(dep)

    missing = []
    if "email" not in best_by_kind: missing.append("e-mail institucional")
    if not any(k in best_by_kind for k in ("phone", "whatsapp")): missing.append("telefone/WhatsApp institucional")
    if "website" not in best_by_kind and not getattr(company, "website", None): missing.append("site oficial")
    if not discovered_departments: missing.append("setor responsável")

    best_channel = channels[0]["kind"] if channels else None
    roles = roles_to_find(company, opportunities or [])
    return {
        "score": score,
        "label": label,
        "best_channel": best_channel,
        "channels_available": len(channels),
        "verified_channels": sum(1 for c in valid if c.status == "verificado"),
        "recommended_departments": departments,
        "departments_found": discovered_departments,
        "roles_to_find": roles,
        "missing": missing,
        "priority_contacts": channels[:8],
        "responsible_search_url": _search_url(company, roles),
        "note": "Contactabilidade mede cobertura de canais institucionais; não é probabilidade de contratação.",
    }


__all__ = ["build_map", "department_from_email", "recommended_departments", "roles_to_find"]
