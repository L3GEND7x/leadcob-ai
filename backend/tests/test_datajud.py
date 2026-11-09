"""DataJud: agregação simulada no formato real da API (respostas observadas em 09/11/2026)."""
from datetime import date

import httpx
import pytest

from app.collectors import datajud
from app.services.segments import DEBT_TYPES


def test_debt_type_assuntos_are_disjoint():
    seen = {}
    for key, dt in DEBT_TYPES.items():
        for n in dt["datajud_assuntos"]:
            assert n not in seen, f"{n} em {seen.get(n)} e {key}"
            seen[n] = key


def test_tribunal_alias():
    assert datajud.tribunal_for("am") == "tjam" and datajud.tribunal_for("DF") == "tjdft"
    with pytest.raises(ValueError):
        datajud.tribunal_for("XX")


def test_months_back():
    assert datajud.months_back(date(2026, 11, 9), 12) == date(2025, 11, 1)
    assert datajud.months_back(date(2026, 2, 15), 3) == date(2025, 11, 1)


AGG = {"hits": {"total": {"value": 29566}}, "aggregations": {
    "classes": {"buckets": [{"key": 81, "doc_count": 12346}, {"key": 12154, "doc_count": 11683}, {"key": 1116, "doc_count": 2806}]},
    "assuntos": {"buckets": [
        {"key": 9582, "doc_count": 11678, "n": {"hits": {"hits": [{"_source": {"assuntos": [{"codigo": 9582, "nome": "Alienação Fiduciária"}]}}]}}},
        {"key": 4980, "doc_count": 2988, "n": {"hits": {"hits": [{"_source": {"assuntos": [{"codigo": 4980, "nome": "Nota Promissória"}]}}]}}},
        {"key": 7703, "doc_count": 1583, "n": {"hits": {"hits": [{"_source": {"assuntos": [{"codigo": 7703, "nome": "Pagamento"}]}}]}}},
        {"key": 10467, "doc_count": 903, "n": {"hits": {"hits": [{"_source": {"assuntos": [{"codigo": 10467, "nome": "Despesas Condominiais"}]}}]}}},
    ]},
    "municipios": {"buckets": [{"key": 1302603, "doc_count": 21755}]},
}}


def test_market_map_with_retry_on_429(monkeypatch):
    monkeypatch.setattr(datajud.time, "sleep", lambda *_: None)
    calls = {"n": 0}
    def handler(req):
        if req.url.host == "brasilapi.com.br":
            assert req.url.params.get("providers")  # sem providers a BrasilAPI respondeu 504
            return httpx.Response(200, json=[{"nome": "MANAUS", "codigo_ibge": "1302603"}])
        calls["n"] += 1
        assert req.url.path == "/api_publica_tjam/_search"
        body = req.read().decode()
        assert "20251101000000" in body and "12154" in body
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": "es_rejected_execution_exception"})
        return httpx.Response(200, json=AGG)
    real = httpx.Client
    monkeypatch.setattr(datajud.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler)))
    d = datajud.market_map("AM", 12, today=date(2026, 11, 9))
    assert calls["n"] == 2 and d["total_processos"] == 29566 and d["tribunal"] == "TJAM"
    tipos = {t["key"]: t["processos"] for t in d["tipos_de_inadimplencia"]}
    assert tipos == {"financiamento_garantia": 11678, "crediario_varejo": 2988, "divida_ativa": 2806, "aluguel_condominio": 903}
    assert [a["nome"] for a in d["assuntos_nao_classificados"]] == ["Pagamento"]
    assert d["municipios"][0] == {"codigo_ibge": "1302603", "nome": "Manaus", "processos": 21755}
    assert any("Não identifica partes" in x for x in d["limites"])


def test_auth_error_is_explicit(monkeypatch):
    real = httpx.Client
    monkeypatch.setattr(datajud.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(401))))
    with pytest.raises(datajud.DataJudError, match="DATAJUD_API_KEY"):
        datajud.market_map("SP", 1)
