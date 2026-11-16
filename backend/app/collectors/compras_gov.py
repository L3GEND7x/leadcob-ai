"""Compras.gov.br Open Data collector — contracts module.

The documented endpoint requires an órgão code and a vigência range. This
collector therefore operates on explicitly supplied órgão codes and filters
contract objects locally for collection / credit-recovery terms.

Source remains Planejada until a live collection is validated.
"""
from __future__ import annotations

import os
import re
import time
from datetime import date

import httpx

from app.services.procurement import relevance_of

BASE_URL = os.getenv("COMPRAS_GOV_API_BASE", "https://dadosabertos.compras.gov.br").rstrip("/")
ENDPOINT = f"{BASE_URL}/modulo-contratos/1_consultarContratos"
USER_AGENT = "LeadCobAI/0.5.3 (consulta a dados abertos do Compras.gov.br)"
PAGE_SIZE = 100
DEFAULT_TERMS = [
    "serviços de cobrança",
    "cobrança extrajudicial",
    "recuperação de crédito",
    "recuperação de créditos",
    "recuperação de ativos",
    "gestão de recebíveis",
]


class ComprasGovUnavailable(RuntimeError):
    pass


def clean(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_contract(row: dict) -> dict:
    obj = clean(row.get("objeto"))
    comp = clean(row.get("informacoesComplementares"))
    return {
        "org_code": clean(row.get("codigoOrgao")) or None,
        "org_name": clean(row.get("nomeOrgao")) or "Órgão público não identificado",
        "management_unit": clean(row.get("nomeUnidadeGestora")) or None,
        "contract_number": clean(row.get("numeroContrato")) or None,
        "object": obj,
        "complement": comp,
        # Supplier identity is deliberately not persisted. The API may represent PF or PJ suppliers,
        # and LeadCob prospecting must not ingest personal identities from this source.
        "start_date": clean(row.get("dataVigenciaInicial")) or None,
        "end_date": clean(row.get("dataVigenciaFinal")) or None,
        "value": row.get("valorGlobal"),
        "pncp_control": clean(row.get("numeroControlePncpContrato")) or None,
        "purchase_id": clean(row.get("idCompra")) or None,
        "deleted": bool(row.get("contratoExcluido")),
        "source_url": ENDPOINT,
    }


def _matches(item: dict, terms: list[str]) -> tuple[bool, list[str], str, str]:
    text = f"{item['object']} {item['complement']}".casefold()
    hits = [term for term in terms if term.casefold() in text]
    relevance, reason = relevance_of(text)
    return bool(hits) and relevance != "descartar", hits, relevance, reason


def request_json(client: httpx.Client, params: dict, attempts: int = 3, pause: float = 1.5) -> dict:
    last = None
    for idx in range(attempts):
        try:
            response = client.get(ENDPOINT, params=params)
            if response.status_code == 429 or response.status_code >= 500:
                raise httpx.HTTPStatusError(f"HTTP {response.status_code}", request=response.request, response=response)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Resposta do Compras.gov.br não é objeto JSON.")
            return payload
        except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
            last = exc
            if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None and 400 <= exc.response.status_code < 500 and exc.response.status_code != 429:
                raise
            if idx < attempts - 1:
                time.sleep(pause * (2 ** idx))
    raise ComprasGovUnavailable(f"{type(last).__name__}: {str(last)[:200]}")


def search_contracts(org_codes: list[str], start_date: str, end_date: str, terms=None,
                     max_pages: int = 3, page_size: int = PAGE_SIZE, pause: float = 0.4) -> dict:
    if not org_codes:
        raise ValueError("Informe ao menos um codigoOrgao.")
    terms = terms or DEFAULT_TERMS
    records = []
    errors = []
    pages_read = 0
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    with httpx.Client(timeout=30.0, headers=headers) as client:
        for org_code in org_codes:
            for page in range(1, max_pages + 1):
                params = {
                    "pagina": page,
                    "tamanhoPagina": page_size,
                    "codigoOrgao": org_code,
                    "dataVigenciaInicialMin": start_date,
                    "dataVigenciaInicialMax": end_date,
                }
                try:
                    payload = request_json(client, params)
                except (ComprasGovUnavailable, httpx.HTTPStatusError) as exc:
                    errors.append(f"órgão {org_code} p.{page}: {exc}")
                    break
                pages_read += 1
                rows = payload.get("resultado") or []
                if not isinstance(rows, list):
                    errors.append(f"órgão {org_code} p.{page}: campo resultado inválido")
                    break
                for raw in rows:
                    if not isinstance(raw, dict):
                        continue
                    item = normalize_contract(raw)
                    if item["deleted"]:
                        continue
                    matched, hits, relevance, reason = _matches(item, terms)
                    if not matched:
                        continue
                    item["matched_terms"] = hits
                    item["relevance"] = relevance
                    item["relevance_reason"] = reason
                    records.append(item)
                total_pages = int(payload.get("totalPaginas") or page)
                if page >= total_pages or len(rows) < page_size:
                    break
                time.sleep(pause)
    return {"records": records, "pages_read": pages_read, "errors": errors,
            "org_codes": org_codes, "date_from": start_date, "date_to": end_date}


__all__ = ["search_contracts", "normalize_contract", "request_json", "ComprasGovUnavailable"]
