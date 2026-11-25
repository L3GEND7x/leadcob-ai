"""Querido Diário collector for municipal gazettes.

The public API is documented at docs.queridodiario.ok.org.br. This connector
normalizes gazette hits into the same procurement classifier used by PNCP.

Until a live collection succeeds in the LeadCob environment, this source must
remain marked as Planejada / [NECESSÁRIO CONFERIR] in config/sources.json.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone

import httpx

from app.services.procurement import classify

BASE_URL = os.getenv("QUERIDO_DIARIO_API_BASE", "https://api.queridodiario.ok.org.br").rstrip("/")
USER_AGENT = "LeadCobAI/0.5.3 (consulta a dados publicos do Querido Diario)"
DEFAULT_TERMS = [
    "serviços de cobrança",
    "cobrança extrajudicial",
    "recuperação de crédito",
    "recuperação de créditos",
    "cobrança de dívida ativa",
]
PAGE_SIZE = 10


class QueridoDiarioUnavailable(RuntimeError):
    pass


def clean(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _excerpt_text(row: dict) -> str:
    excerpts = row.get("excerpts") or []
    if isinstance(excerpts, str):
        return clean(excerpts)
    parts = []
    if isinstance(excerpts, list):
        for item in excerpts:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text") or item.get("excerpt") or item.get("content") or "")
    return clean(" ".join(parts))


def normalize_gazette(row: dict, matched_term: str) -> dict:
    territory_name = clean(row.get("territory_name")) or "Município não identificado"
    state = clean(row.get("state_code")) or None
    date = clean(row.get("date")) or None
    url = clean(row.get("url")) or None
    excerpt = _excerpt_text(row)
    evidence = excerpt or f"Diário oficial municipal contém o termo de busca '{matched_term}'."
    item = {
        "company_name": f"Município de {territory_name}" if territory_name != "Município não identificado" else territory_name,
        "cnpj": None,
        "unit_name": None,
        "city": territory_name if territory_name != "Município não identificado" else None,
        "state": state,
        "object": evidence,
        "complement": "",
        "title": (evidence or "Publicação em diário oficial municipal")[:240],
        "control": None,
        "year": date[:4] if date and len(date) >= 4 else None,
        "sequential": None,
        "modality_id": None,
        "modality_name": "Diário oficial municipal",
        "situation": "Publicação em diário oficial",
        "published": date,
        "deadline": None,
        "estimated_value": None,
        "origin_url": url,
        "url": url,
        "evidence_level": "fonte_primaria_diario",
        "matched_terms": [matched_term],
        "territory_id": clean(row.get("territory_id")) or None,
        "edition_number": clean(row.get("edition_number")) or None,
    }
    item.update(classify(item))
    # A ausência de prazo/edital estruturado impede tratar o achado como oportunidade comprovada.
    item["commercial_signal"] = "sinal_a_confirmar"
    return item


def request_json(client: httpx.Client, params: dict, attempts: int = 3, pause: float = 1.5) -> dict:
    last = None
    for idx in range(attempts):
        try:
            response = client.get(f"{BASE_URL}/gazettes", params=params)
            if response.status_code == 429 or response.status_code >= 500:
                raise httpx.HTTPStatusError(f"HTTP {response.status_code}", request=response.request, response=response)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Resposta do Querido Diário não é objeto JSON.")
            return payload
        except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
            last = exc
            if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None and 400 <= exc.response.status_code < 500 and exc.response.status_code != 429:
                raise
            if idx < attempts - 1:
                time.sleep(pause * (2 ** idx))
    raise QueridoDiarioUnavailable(f"{type(last).__name__}: {str(last)[:200]}")


def search_gazettes(territory_ids: list[str], terms=None, size: int = PAGE_SIZE,
                    max_pages: int = 1, pause: float = 1.1) -> dict:
    if not territory_ids:
        raise ValueError("Informe ao menos um código IBGE municipal em territory_ids.")
    terms = terms or DEFAULT_TERMS
    records = []
    errors = []
    pages_read = 0
    seen = set()
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    with httpx.Client(timeout=30.0, headers=headers) as client:
        for term in terms:
            for page in range(max_pages):
                params = {
                    "territory_ids": ",".join(territory_ids),
                    "querystring": term,
                    "excerpt_size": 500,
                    "number_of_excerpts": 1,
                    "size": size,
                    "offset": page * size,
                }
                try:
                    payload = request_json(client, params)
                except (QueridoDiarioUnavailable, httpx.HTTPStatusError) as exc:
                    errors.append(f"'{term}' p.{page + 1}: {exc}")
                    break
                gazettes = payload.get("gazettes")
                total = payload.get("total_gazettes")
                if (not isinstance(gazettes, list)
                        or any(not isinstance(raw, dict) for raw in gazettes)
                        or (total is not None and (type(total) is not int or total < 0))):
                    errors.append(f"'{term}' p.{page + 1}: estrutura de diários inválida")
                    break
                pages_read += 1
                for raw in gazettes:
                    item = normalize_gazette(raw, term)
                    key = (item.get("territory_id"), item.get("published"), item.get("url"), item.get("object"))
                    if key in seen:
                        continue
                    seen.add(key)
                    records.append(item)
                total = total if total is not None else len(gazettes)
                if len(gazettes) < size or (page + 1) * size >= total:
                    break
                time.sleep(pause)
    return {"records": records, "pages_read": pages_read, "errors": errors, "terms": terms,
            "territory_ids": territory_ids}


__all__ = ["search_gazettes", "normalize_gazette", "request_json", "QueridoDiarioUnavailable"]
