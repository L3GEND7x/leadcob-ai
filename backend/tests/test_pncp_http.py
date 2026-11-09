"""Contrato HTTP do coletor com transporte simulado (sem rede)."""
from datetime import datetime, timezone

import httpx
import pytest

from app.collectors import pncp

NOW = datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(pncp.time, "sleep", lambda *_: None)


def use(monkeypatch, handler):
    monkeypatch.setattr(pncp, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def test_scan_uses_page_size_accepted_by_api(monkeypatch):
    seen = []
    def handler(req):
        seen.append(req.url.params["tamanhoPagina"])
        if req.url.params["tamanhoPagina"] != "50":  # comportamento real: 400
            return httpx.Response(400, json={"message": "Tamanho de página inválido"})
        return httpx.Response(200, json={"data": [], "totalRegistros": 0, "totalPaginas": 0})
    use(monkeypatch, handler)
    out = pncp.scan_publications(days=7, max_pages=1, now=NOW)
    assert set(seen) == {"50"} and not out["errors"]


def test_scan_one_bad_modality_does_not_abort_run(monkeypatch):
    def handler(req):
        if req.url.params["codigoModalidadeContratacao"] == "4":
            return httpx.Response(400, json={"message": "erro"})
        rows = [{"numeroControlePNCP": "12345678000199-1-000001/2026", "objetoCompra": "serviços de cobrança extrajudicial",
                 "orgaoEntidade": {"cnpj": "12345678000199", "razaoSocial": "ORGAO"}, "modalidadeId": 6,
                 "dataEncerramentoProposta": "2026-12-01T09:00:00"}] if req.url.params["codigoModalidadeContratacao"] == "6" else []
        return httpx.Response(200, json={"data": rows, "totalRegistros": len(rows), "totalPaginas": 1})
    use(monkeypatch, handler)
    out = pncp.scan_publications(max_pages=1, now=NOW)
    assert len(out["errors"]) == 1 and len(out["records"]) == 1
    assert out["records"][0]["commercial_signal"] == "oportunidade_comprovada"


def test_retries_on_empty_reply(monkeypatch):
    calls = {"n": 0}
    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.", request=req)
        return httpx.Response(200, json={"ok": True})
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        assert pncp.request_json(c, "https://pncp.gov.br/x", pause=0) == {"ok": True}
    assert calls["n"] == 3


def test_search_then_confirm(monkeypatch):
    def handler(req):
        if req.url.path == "/api/search/":
            q = req.url.params["q"]
            items = []
            if q == '"cobrança extrajudicial"':
                items = [
                    {"numero_controle_pncp": "11111111000111-1-000010/2026", "orgao_cnpj": "11111111000111", "ano": "2026",
                     "numero_sequencial": "10", "orgao_nome": "SECRETARIA X", "uf": "SP",
                     "description": "credenciamento para serviços de cobrança extrajudicial",
                     "modalidade_licitacao_id": "12", "data_fim_vigencia": "2027-08-04T09:59"},
                    {"numero_controle_pncp": "22222222000122-1-000003/2026", "orgao_cnpj": "22222222000122", "ano": "2026",
                     "numero_sequencial": "3", "orgao_nome": "MUNICIPIO Y", "uf": "MG",
                     "description": "serviços de cobrança automática de pedágios", "modalidade_licitacao_id": "6",
                     "data_fim_vigencia": "2026-11-26T09:30"},
                ]
            return httpx.Response(200, json={"total": len(items), "items": items})
        if req.url.path == "/api/consulta/v1/orgaos/11111111000111/compras/2026/10":
            return httpx.Response(200, json={"numeroControlePNCP": "11111111000111-1-000010/2026",
                                             "objetoCompra": "credenciamento para serviços de cobrança extrajudicial",
                                             "dataEncerramentoProposta": "2027-08-04T09:59:00", "modalidadeId": 12,
                                             "valorTotalEstimado": 250000.0, "linkSistemaOrigem": "https://exemplo.sp.gov.br"})
        raise AssertionError(f"chamada inesperada: {req.url}")  # o pedágio não deve ser confirmado
    use(monkeypatch, handler)
    out = pncp.search_opportunities(max_pages=1, now=NOW)
    by = {r["control"]: r for r in out["records"]}
    good = by["11111111000111-1-000010/2026"]
    assert good["evidence_level"] == "confirmada_api_oficial" and good["commercial_signal"] == "oportunidade_comprovada"
    assert good["estimated_value"] == 250000.0
    assert by["22222222000122-1-000003/2026"]["relevance"] == "descartar"
    assert out["confirmed"] == 1 and not out["errors"]
