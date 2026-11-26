"""Malformed, empty and truncated PNCP responses must have distinct outcomes."""
from datetime import datetime, timezone
import httpx
import pytest
from app.collectors import pncp

NOW = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
ROW = {"numeroControlePNCP":"12345678000195-1-000001/2026", "objetoCompra":"serviços de cobrança",
       "orgaoEntidade":{"cnpj":"12345678000195", "razaoSocial":"Fixture"}}


def transport(monkeypatch, payload, status=200):
    monkeypatch.setattr(pncp, "SCAN_MODALITIES", [4])
    monkeypatch.setattr(pncp, "_client", lambda: httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, json=payload) if status == 200 else httpx.Response(status))))


@pytest.mark.parametrize("payload", [{}, [], {"data":[]}, {"data":[],"totalRegistros":2,"totalPaginas":1},
    {"data":[None],"totalRegistros":1,"totalPaginas":1},
    {"data":[{}],"totalRegistros":1,"totalPaginas":1},
    {"data":[ROW],"totalRegistros":1,"totalPaginas":"oops"},
    {"data":[ROW],"totalRegistros":True,"totalPaginas":1}])
def test_malformed_scan_is_not_a_successful_empty_capture(monkeypatch, payload):
    transport(monkeypatch,payload)
    result=pncp.scan_publications(max_pages=1,pause=0,now=NOW)
    assert result["pages_read"] == 0 and result["errors"]
    assert not result["coverage_complete"] and not result["records"]


@pytest.mark.parametrize("status", [200,204,404])
def test_legitimate_empty_scan_is_successful(monkeypatch,status):
    transport(monkeypatch,{"data":[],"totalRegistros":0,"totalPaginas":0},status)
    result=pncp.scan_publications(max_pages=1,pause=0,now=NOW)
    assert result["pages_read"] == 1 and result["errors"] == []
    assert result["records_read"] == 0 and result["coverage_complete"]
    assert result["date_to"] == "2026-11-26"


def test_capped_scan_reports_real_records_and_partial_coverage(monkeypatch):
    transport(monkeypatch,{"data":[ROW]*50,"totalRegistros":1000,"totalPaginas":20})
    result=pncp.scan_publications(max_pages=1,pause=0,now=NOW)
    assert result["records_read"] == 50 and result["total_available"] == 1000
    assert len(result["records"]) == 1  # control-number deduplication
    assert result["errors"] == ["modalidade 4: coverage_limited"]
    assert not result["coverage_complete"]


def test_small_final_page_count_is_not_rounded_up_to_fifty(monkeypatch):
    transport(monkeypatch,{"data":[ROW],"totalRegistros":1,"totalPaginas":1})
    result=pncp.scan_publications(max_pages=1,pause=0,now=NOW)
    assert result["records_read"] == 1
    assert result["coverage_note"].startswith("1 de 1 ")
    assert not result["errors"]


@pytest.mark.parametrize("payload", [{}, {"items":[],"total":10}, {"items":[{}],"total":1}])
def test_invalid_search_snapshot_is_not_success(monkeypatch,payload):
    transport(monkeypatch,payload)
    result=pncp.search_opportunities(terms=["cobrança"],max_pages=1,pause=0,now=NOW)
    assert result["pages_read"] == 0 and result["errors"]


def test_page_cap_on_search_is_not_full_coverage(monkeypatch):
    item={"numero_controle_pncp":ROW["numeroControlePNCP"],"description":"serviços de cobrança"}
    transport(monkeypatch,{"items":[item]*100,"total":101})
    result=pncp.search_opportunities(terms=["cobrança"],max_pages=1,pause=0,confirm=False,now=NOW)
    assert result["errors"] == ["busca 'cobrança': coverage_limited"]
