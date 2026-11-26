"""Coletor PNCP — v0.2.1.

Duas etapas, com papéis distintos:

1. DESCOBERTA (`/api/search/`): índice de busca textual que o próprio portal
   pncp.gov.br usa. Permite procurar termos em âmbito nacional sem varrer
   dezenas de milhares de registros. NÃO consta do manual da API de consulta;
   pode mudar sem aviso. Resultado = indício.
2. CONFIRMAÇÃO (`/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}`):
   API oficial de consulta. Confirma que a contratação existe e traz objeto,
   prazo de propostas, valor estimado e link do sistema de origem.

Modo alternativo `varredura` usa o endpoint documentado
`/v1/contratacoes/publicacao` por data e modalidade (cobertura limitada pelo
número de páginas — útil como contingência se a busca sair do ar).

Observações verificadas contra a API real em 09/11/2026:
- `/v1/contratacoes/publicacao` rejeita `tamanhoPagina=100` com HTTP 400
  ("Tamanho de página inválido"); 50 é aceito.
- A busca devolve respostas vazias intermitentes (RemoteProtocolError) e passa
  a recusar conexões após rajadas: retentativa com espera é obrigatória.
"""
from __future__ import annotations

import os
import re
import time
from datetime import date, datetime, timedelta, timezone

import httpx

from app.services.procurement import classify, parse_dt

SITE = os.getenv("PNCP_SITE", "https://pncp.gov.br").rstrip("/")
BASE_URL = os.getenv("PNCP_API_BASE", f"{SITE}/api/consulta").rstrip("/")
SEARCH_URL = f"{SITE}/api/search/"
PAGE_SIZE_PUBLICACAO = 50  # máximo aceito pelo endpoint /contratacoes/publicacao
PAGE_SIZE_SEARCH = 100
USER_AGENT = "LeadCobAI/0.2.1 (consulta a dados publicos do PNCP)"

# Termos de descoberta (busca exata entre aspas). A aderência real é decidida
# depois pelo classificador, sobre o objeto da contratação.
DEFAULT_TERMS = [
    "serviços de cobrança",
    "cobrança extrajudicial",
    "cobrança administrativa",
    "recuperação de crédito",
    "recuperação de créditos",
    "gestão de recebíveis",
    "cobrança de dívida ativa",
    "dívida ativa",
    "recuperação de ativos",
    "inadimplência",
]
SCAN_MODALITIES = [4, 6, 8, 9, 10, 12]


class PNCPUnavailable(RuntimeError):
    """A API não respondeu após todas as retentativas."""


def clean(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def only_alnum(value) -> str | None:
    v = re.sub(r"[^0-9A-Za-z]", "", clean(value)).upper()
    return v or None


def edital_url(cnpj, ano, seq) -> str:
    if cnpj and ano and seq:
        return f"{SITE}/app/editais/{cnpj}/{ano}/{seq}"
    return f"{SITE}/app/editais"


def split_control(control: str):
    """'06988976000109-1-000008/2026' -> ('06988976000109', '2026', '8')."""
    m = re.match(r"^(\d{14})-\d+-(\d+)/(\d{4})$", clean(control))
    if not m:
        return None, None, None
    return m.group(1), m.group(3), str(int(m.group(2)))


def request_json(client: httpx.Client, url: str, params=None, attempts: int = 4, pause: float = 2.0):
    """GET com retentativa/backoff. Devolve None para 204/404."""
    last = None
    for i in range(attempts):
        try:
            r = client.get(url, params=params)
            if r.status_code in (204, 404):
                return None
            if r.status_code == 429 or r.status_code >= 500:
                raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
            r.raise_for_status()  # 4xx restantes = erro de contrato: não adianta repetir
            return r.json()
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and 400 <= exc.response.status_code < 500 and exc.response.status_code != 429:
                raise
            last = exc
        except (httpx.TransportError, ValueError) as exc:
            last = exc
        if i < attempts - 1:
            time.sleep(pause * (2 ** i))
    raise PNCPUnavailable(f"{type(last).__name__}: {str(last)[:200]}")


def _page(payload, field, total_field):
    """Reject malformed snapshots instead of reporting successful empty capture."""
    if payload is None:  # request_json accepts only HTTP 204/404 as absent
        return [], 0
    if not isinstance(payload, dict) or not isinstance(payload.get(field), list):
        raise ValueError("invalid_page_shape")
    rows = payload[field]
    total = payload.get(total_field)
    if type(total) is not int or total < 0 or total < len(rows):
        raise ValueError("invalid_page_total")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("invalid_page_record")
    if not rows and total:
        raise ValueError("incomplete_page")
    return rows, total


# ---------------------------------------------------------------- normalização
def normalize_record(row: dict) -> dict:
    """Registro da API oficial de consulta (publicação ou detalhe)."""
    org = row.get("orgaoEntidade") or {}
    unit = row.get("unidadeOrgao") or {}
    obj = clean(row.get("objetoCompra") or row.get("objeto") or row.get("descricao"))
    control = clean(row.get("numeroControlePNCP") or row.get("numeroControlePncp"))
    cnpj = only_alnum(org.get("cnpj") or row.get("cnpjOrgao"))
    c_cnpj, c_ano, c_seq = split_control(control)
    ano = clean(row.get("anoCompra")) or c_ano
    seq = clean(row.get("sequencialCompra")) or c_seq
    return {
        "company_name": clean(org.get("razaoSocial") or org.get("razaosocial") or row.get("nomeOrgao")) or "Órgão público não identificado",
        "cnpj": cnpj or c_cnpj,
        "unit_name": clean(unit.get("nomeUnidade")) or None,
        "city": clean(unit.get("municipioNome")) or None,
        "state": clean(unit.get("ufSigla")) or None,
        "object": obj,
        "complement": clean(row.get("informacaoComplementar")),
        "title": (obj or "Contratação pública")[:240],
        "control": control,
        "year": ano,
        "sequential": seq,
        "modality_id": row.get("modalidadeId") or row.get("codigoModalidadeContratacao"),
        "modality_name": clean(row.get("modalidadeNome")) or None,
        "situation": clean(row.get("situacaoCompraNome")) or None,
        "published": clean(row.get("dataPublicacaoPncp")),
        "deadline": clean(row.get("dataEncerramentoProposta")) or None,
        "estimated_value": row.get("valorTotalEstimado"),
        "origin_url": clean(row.get("linkSistemaOrigem") or row.get("linkProcessoEletronico")) or None,
        "url": edital_url(cnpj or c_cnpj, ano, seq),
    }


def normalize_search_item(item: dict) -> dict:
    """Item do índice de busca (/api/search/)."""
    control = clean(item.get("numero_controle_pncp"))
    cnpj = only_alnum(item.get("orgao_cnpj"))
    ano, seq = clean(item.get("ano")), clean(item.get("numero_sequencial"))
    obj = clean(item.get("description"))
    return {
        "company_name": clean(item.get("orgao_nome")) or "Órgão público não identificado",
        "cnpj": cnpj,
        "unit_name": clean(item.get("unidade_nome")) or None,
        "city": clean(item.get("municipio_nome")) or None,
        "state": clean(item.get("uf")) or None,
        "object": obj,
        "complement": "",
        "title": (obj or clean(item.get("title")) or "Contratação pública")[:240],
        "control": control,
        "year": ano,
        "sequential": seq,
        "modality_id": item.get("modalidade_licitacao_id"),
        "modality_name": clean(item.get("modalidade_licitacao_nome")) or None,
        "situation": clean(item.get("situacao_nome")) or None,
        "published": clean(item.get("data_publicacao_pncp")),
        # No índice, `data_fim_vigencia` do edital corresponde ao fim do
        # recebimento de propostas; é substituído pelo dado oficial na confirmação.
        "deadline": clean(item.get("data_fim_vigencia")) or None,
        "estimated_value": item.get("valor_global"),
        "origin_url": None,
        "url": edital_url(cnpj, ano, seq),
    }


def merge_official(found: dict, official: dict) -> dict:
    """Sobrepõe o indício da busca com os campos da API oficial."""
    merged = dict(found)
    for key, value in normalize_record(official).items():
        if value not in (None, "") and key != "url":
            merged[key] = value
    return merged


# ------------------------------------------------------------------- coleta
def _client() -> httpx.Client:
    return httpx.Client(timeout=30.0, headers={"Accept": "application/json", "User-Agent": USER_AGENT})


def _finish(item: dict, matched: list[str], now: datetime) -> dict:
    result = classify(item, now=now)
    item.update(result)
    item["matched_terms"] = matched
    return item


def search_opportunities(terms=None, only_open: bool = True, max_pages: int = 2, confirm: bool = True,
                         pause: float = 1.2, now: datetime | None = None) -> dict:
    """Descoberta nacional pelo índice de busca + confirmação na API oficial."""
    now = now or datetime.now(timezone.utc)
    terms = terms or DEFAULT_TERMS
    found: dict[str, dict] = {}
    matched: dict[str, list[str]] = {}
    errors: list[str] = []
    pages_read = 0
    with _client() as client:
        for term in terms:
            for page in range(1, max_pages + 1):
                params = {"q": f'"{term}"', "tipos_documento": "edital", "ordenacao": "-data",
                          "pagina": page, "tam_pagina": PAGE_SIZE_SEARCH,
                          "status": "recebendo_proposta" if only_open else "todos"}
                try:
                    payload = request_json(client, SEARCH_URL, params)
                except (PNCPUnavailable, httpx.HTTPStatusError) as exc:
                    errors.append(f"busca '{term}' p.{page}: {exc}")
                    break
                try:
                    items, total = _page(payload, "items", "total")
                    if any(not clean(row.get("numero_controle_pncp")) or not clean(row.get("description")) for row in items):
                        raise ValueError("invalid_search_record")
                except ValueError as exc:
                    errors.append(f"busca '{term}' p.{page}: {exc}")
                    break
                pages_read += 1
                for raw in items:
                    if not isinstance(raw, dict):
                        continue
                    item = normalize_search_item(raw)
                    key = item["control"] or (item["company_name"] + item["object"][:80])
                    found.setdefault(key, item)
                    matched.setdefault(key, [])
                    if term not in matched[key]:
                        matched[key].append(term)
                time.sleep(pause)
                if page * PAGE_SIZE_SEARCH >= total:
                    break
                if len(items) < PAGE_SIZE_SEARCH or page == max_pages:
                    errors.append(f"busca '{term}': coverage_limited")
                    break

        records, confirmed = [], 0
        for key, item in found.items():
            # Só confirma o que tem chance de ser aderente: economiza chamadas.
            pre = classify(item, now=now)
            if confirm and pre["relevance"] != "descartar" and item["cnpj"] and item["year"] and item["sequential"]:
                url = f"{BASE_URL}/v1/orgaos/{item['cnpj']}/compras/{item['year']}/{item['sequential']}"
                try:
                    official = request_json(client, url)
                except (PNCPUnavailable, httpx.HTTPStatusError) as exc:
                    official = None
                    errors.append(f"confirmação {item['control']}: {exc}")
                if official and (not isinstance(official, dict)
                        or clean(official.get("numeroControlePNCP")) != item["control"]
                        or not clean(official.get("objetoCompra") or official.get("objeto"))):
                    errors.append(f"confirmação {item['control']}: invalid_official_record")
                    official = None
                if official:
                    item = merge_official(item, official)
                    item["evidence_level"] = "confirmada_api_oficial"
                    confirmed += 1
                time.sleep(pause)
            item.setdefault("evidence_level", "indicio_busca")
            records.append(_finish(item, matched[key], now))
    return {"mode": "busca", "records": records, "pages_read": pages_read, "confirmed": confirmed,
            "errors": errors, "terms": terms, "only_open": only_open}


def scan_publications(days: int = 7, max_pages: int = 2, terms=None, pause: float = 0.3,
                      now: datetime | None = None) -> dict:
    """Contingência: varredura do endpoint documentado por data de publicação.

    Cobertura parcial: cada página tem 50 registros e só `max_pages` páginas por
    modalidade são lidas (um pregão eletrônico pode ter centenas de páginas em
    14 dias). O filtro textual é aplicado localmente.
    """
    now = now or datetime.now(timezone.utc)
    end = now.date()
    start = end - timedelta(days=days)
    base = {"dataInicial": start.strftime("%Y%m%d"), "dataFinal": end.strftime("%Y%m%d"),
            "tamanhoPagina": PAGE_SIZE_PUBLICACAO}
    folded = [t.casefold() for t in (terms or DEFAULT_TERMS)]
    records, seen, errors, pages_read, total_available, records_read = [], set(), [], 0, 0, 0
    with _client() as client:
        for modality in SCAN_MODALITIES:
            for page in range(1, max_pages + 1):
                params = {**base, "codigoModalidadeContratacao": modality, "pagina": page}
                try:
                    payload = request_json(client, f"{BASE_URL}/v1/contratacoes/publicacao", params)
                except (PNCPUnavailable, httpx.HTTPStatusError) as exc:
                    errors.append(f"modalidade {modality} p.{page}: {exc}")
                    break
                try:
                    rows, total = _page(payload, "data", "totalRegistros")
                    page_count = payload.get("totalPaginas") if payload is not None else 0
                    if type(page_count) is not int or page_count < 0 or (rows and not page_count):
                        raise ValueError("invalid_page_count")
                    if any(not clean(row.get("numeroControlePNCP") or row.get("numeroControlePncp"))
                           or not clean(row.get("objetoCompra") or row.get("objeto") or row.get("descricao"))
                           or not isinstance(row.get("orgaoEntidade") or {}, dict)
                           or not isinstance(row.get("unidadeOrgao") or {}, dict) for row in rows):
                        raise ValueError("invalid_publication_record")
                except ValueError as exc:
                    errors.append(f"modalidade {modality} p.{page}: {exc}")
                    break
                pages_read += 1
                records_read += len(rows)
                if page == 1:
                    total_available += total
                for raw in rows:
                    if not isinstance(raw, dict):
                        continue
                    item = normalize_record(raw)
                    text = f"{item['object']} {item['complement']}".casefold()
                    hits = [t for t in folded if t in text]
                    if not hits or item["control"] in seen:
                        continue
                    seen.add(item["control"])
                    item["evidence_level"] = "confirmada_api_oficial"
                    records.append(_finish(item, hits, now))
                time.sleep(pause)
                if page >= page_count and page * PAGE_SIZE_PUBLICACAO >= total:
                    break
                if len(rows) < PAGE_SIZE_PUBLICACAO or page == max_pages:
                    errors.append(f"modalidade {modality}: coverage_limited")
                    break
    return {"mode": "varredura", "records": records, "pages_read": pages_read, "confirmed": len(records),
            "errors": errors, "date_from": start.isoformat(), "date_to": end.isoformat(),
            "records_read": records_read, "total_available": total_available,
            "coverage_complete": not errors,
            "coverage_note": f"{records_read} de {total_available} registros publicados nas modalidades consultadas foram lidos; não representa cobertura integral do PNCP."}


# Compatibilidade com a v0.2
def fetch_opportunities(days=7, max_pages=2, terms=None):
    return scan_publications(days=days, max_pages=max_pages, terms=terms)


__all__ = ["search_opportunities", "scan_publications", "fetch_opportunities", "normalize_record",
           "normalize_search_item", "merge_official", "split_control", "parse_dt", "PNCPUnavailable"]
