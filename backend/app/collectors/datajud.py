"""DataJud (CNJ) — mapa de inadimplência judicializada por UF, tipo de dívida e município.

API pública: https://datajud-wiki.cnj.jus.br/api-publica/ (Elasticsearch, POST /api_publica_{tribunal}/_search,
cabeçalho "Authorization: APIKey <chave pública publicada pelo CNJ>").

O QUE ESTA FONTE NÃO FAZ: identificar empresas. Por desenho, a API pública resguarda
"dados de partes" (texto da documentação oficial, verificado em 09/11/2026); os campos
devolvidos são classe, assuntos, órgão julgador, datas e movimentos. Logo, o DataJud
mede ONDE e QUE TIPO de inadimplência está sendo cobrada na Justiça — não QUEM cobra.

Códigos de classe conferidos na própria API (TJAM/TJSP, 09/11/2026).
"""
from __future__ import annotations

import os
import time
from datetime import date

import httpx

from app.services.segments import DEBT_TYPES, SEGMENTS

BASE_URL = os.getenv("DATAJUD_API_URL", "https://api-publica.datajud.cnj.jus.br").rstrip("/")
# Chave PÚBLICA publicada pelo CNJ em https://datajud-wiki.cnj.jus.br/api-publica/acesso
# (conferida em 09/11/2026). O CNJ avisa que ela pode mudar a qualquer momento: em caso de
# HTTP 401/403, atualize DATAJUD_API_KEY com o valor atual daquela página.
API_KEY = os.getenv("DATAJUD_API_KEY", "")

COLLECTION_CLASSES = {
    12154: "Execução de Título Extrajudicial",
    40: "Monitória",
    81: "Busca e Apreensão em Alienação Fiduciária",
    93: "Despejo por Falta de Pagamento",
    94: "Despejo por Falta de Pagamento Cumulado Com Cobrança",
    1116: "Execução Fiscal",
}
UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI",
       "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]


class DataJudError(RuntimeError):
    pass


# Índices conferidos nas 27 UFs em 09/11/2026 (api_publica_tj{uf}; DF = tjdft), com o total histórico
# de Execuções de Título Extrajudicial, de 13.040 (TJRR) a 1.498.166 (TJMG).
def tribunal_for(uf: str) -> str:
    uf = uf.upper()
    if uf not in UFS:
        raise ValueError(f"UF inválida: {uf}")
    return "tjdft" if uf == "DF" else f"tj{uf.lower()}"


def _post(client: httpx.Client, tribunal: str, body: dict, attempts: int = 5, pause: float = 8.0) -> dict:
    last = None
    for i in range(attempts):
        try:
            r = client.post(f"{BASE_URL}/api_publica_{tribunal}/_search", json=body)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (401, 403):
                raise DataJudError("Chave da API pública recusada: atualize DATAJUD_API_KEY "
                                   "(https://datajud-wiki.cnj.jus.br/api-publica/acesso).")
            last = f"HTTP {r.status_code}"  # 429 = fila do Elasticsearch cheia no CNJ
        except httpx.TransportError as exc:
            last = type(exc).__name__
        time.sleep(pause * (i + 1))
    raise DataJudError(f"DataJud não respondeu após {attempts} tentativas ({last}).")


def months_back(today: date, months: int) -> date:
    y, m = today.year, today.month - months
    while m <= 0:
        m += 12; y -= 1
    return date(y, m, 1)


def debt_type_totals(assuntos: list[dict], classes: list[dict]) -> dict:
    """Soma os assuntos por tipo de inadimplência (cada assunto em um único tipo).
    Dívida ativa vem da classe Execução Fiscal. Um processo pode ter vários assuntos."""
    by_name = {}
    for key, dt in DEBT_TYPES.items():
        for n in dt["datajud_assuntos"]:
            by_name[n.strip().casefold()] = key
    totals: dict[str, dict] = {}
    unclassified = []
    for a in assuntos:
        key = by_name.get((a["nome"] or "").strip().casefold())
        if not key:
            unclassified.append(a)
            continue
        t = totals.setdefault(key, {"processos": 0, "assuntos": []})
        t["processos"] += a["processos"]
        if a["nome"] not in t["assuntos"]:
            t["assuntos"].append(a["nome"])
    for key, dt in DEBT_TYPES.items():
        for code in dt.get("datajud_classes", []):
            n = sum(c["processos"] for c in classes if c["codigo"] == code)
            if n:
                t = totals.setdefault(key, {"processos": 0, "assuntos": []})
                t["processos"] += n
                t["assuntos"].append(f"classe {COLLECTION_CLASSES.get(code, code)}")
    out = [{"key": k, "label": DEBT_TYPES[k]["label"], **v,
            "perfis_relacionados": [s for s, seg in SEGMENTS.items() if k in seg.get("debt_types", [])]}
           for k, v in totals.items()]
    return {"tipos": sorted(out, key=lambda x: -x["processos"]),
            "nao_classificados": sorted(unclassified, key=lambda x: -x["processos"])}


def municipality_names(uf: str, client: httpx.Client | None = None) -> dict[str, str]:
    own = client is None
    client = client or httpx.Client(timeout=20)
    try:
        # Sem "providers" a BrasilAPI respondeu HTTP 504 em 09/11/2026; com ele, 200.
        for attempt in range(3):
            r = client.get(f"https://brasilapi.com.br/api/ibge/municipios/v1/{uf.upper()}",
                           params={"providers": "dados-abertos-br,gov,wikipedia"})
            if r.status_code == 200:
                return {str(m["codigo_ibge"]): m["nome"].title() for m in r.json()}
            time.sleep(2 * (attempt + 1))
        return {}
    except Exception:
        return {}
    finally:
        if own:
            client.close()


def _debt(assuntos, classes):
    d = debt_type_totals(assuntos, classes)
    return {"tipos_de_inadimplencia": d["tipos"], "assuntos_nao_classificados": d["nao_classificados"]}


def market_map(uf: str, months: int = 12, today: date | None = None, client: httpx.Client | None = None) -> dict:
    today = today or date.today()
    start = months_back(today, months)
    tribunal = tribunal_for(uf)
    body = {
        "size": 0, "track_total_hits": True,
        "query": {"bool": {"filter": [
            {"terms": {"classe.codigo": list(COLLECTION_CLASSES)}},
            {"range": {"dataAjuizamento": {"gte": start.strftime("%Y%m%d000000"), "lt": today.strftime("%Y%m%d235959")}}},
        ]}},
        "aggs": {
            "classes": {"terms": {"field": "classe.codigo", "size": len(COLLECTION_CLASSES)}},
            "assuntos": {"terms": {"field": "assuntos.codigo", "size": 40},
                         "aggs": {"n": {"top_hits": {"size": 1, "_source": ["assuntos"]}}}},
            "municipios": {"terms": {"field": "orgaoJulgador.codigoMunicipioIBGE", "size": 30}},
        },
    }
    own = client is None
    if own and not API_KEY:
        raise DataJudError("Configure DATAJUD_API_KEY com a chave pública atual do CNJ antes da consulta.")
    client = client or httpx.Client(timeout=120, headers={"Authorization": f"APIKey {API_KEY}", "Content-Type": "application/json",
                                                          "User-Agent": "LeadCobAI/0.4 (pesquisa de mercado)"})
    try:
        data = _post(client, tribunal, body)
    finally:
        if own:
            client.close()
    aggs = data.get("aggregations", {})
    classes = [{"codigo": b["key"], "nome": COLLECTION_CLASSES.get(b["key"], str(b["key"])), "processos": b["doc_count"]}
               for b in aggs.get("classes", {}).get("buckets", [])]
    assuntos = []
    for b in aggs.get("assuntos", {}).get("buckets", []):
        src = (b.get("n", {}).get("hits", {}).get("hits") or [{}])[0].get("_source", {})
        nome = next((a.get("nome") for a in src.get("assuntos", []) if isinstance(a, dict) and a.get("codigo") == b["key"]), None)
        assuntos.append({"codigo": b["key"], "nome": nome, "processos": b["doc_count"]})
    names = municipality_names(uf)
    municipios = [{"codigo_ibge": str(b["key"]), "nome": names.get(str(b["key"])), "processos": b["doc_count"]}
                  for b in aggs.get("municipios", {}).get("buckets", [])]
    return {
        "fonte": "DataJud (CNJ) — API pública", "tribunal": tribunal.upper(), "uf": uf.upper(),
        "periodo": {"inicio": start.isoformat(), "fim": today.isoformat(), "criterio": "data de ajuizamento"},
        "total_processos": data.get("hits", {}).get("total", {}).get("value"),
        "classes": classes, "assuntos": assuntos, **_debt(assuntos, classes),
        "municipios": municipios,
        "limites": ["Não identifica partes: mostra volume e tipo de cobrança judicial, não quais empresas cobram.",
                    "Cobre só a Justiça Estadual (TJ) da UF; execuções fiscais federais e Justiça Federal não entram.",
                    "Um processo pode ter vários assuntos: as somas por assunto não são exclusivas."],
    }
