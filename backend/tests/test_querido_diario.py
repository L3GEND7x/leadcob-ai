from datetime import datetime, timezone

import httpx

from app.collectors import querido_diario


def test_normalize_gazette_uses_procurement_classifier_and_keeps_source():
    row = {
        "territory_id": "1302603",
        "territory_name": "Manaus",
        "state_code": "AM",
        "date": "2026-11-10",
        "url": "https://example.org/diario.pdf",
        "edition_number": "123",
        "excerpts": [{"text": "Contratação de serviços de cobrança extrajudicial e recuperação de crédito."}],
    }
    item = querido_diario.normalize_gazette(row, "cobrança extrajudicial")
    assert item["company_name"] == "Município de Manaus"
    assert item["state"] == "AM"
    assert item["source" if "source" in item else "url"] == "https://example.org/diario.pdf"
    assert item["relevance"] in ("alta", "revisar")
    assert item["commercial_signal"] == "sinal_a_confirmar"
    assert item["evidence_level"] == "fonte_primaria_diario"


def test_search_gazettes_parses_documented_shape(monkeypatch):
    payload = {
        "total_gazettes": 1,
        "gazettes": [{
            "territory_id": "1302603",
            "territory_name": "Manaus",
            "state_code": "AM",
            "date": "2026-11-10",
            "url": "https://example.org/diario.pdf",
            "excerpts": ["serviços de cobrança extrajudicial"],
        }],
    }

    class FakeResponse:
        status_code = 200
        request = httpx.Request("GET", "https://example.org")
        def raise_for_status(self):
            return None
        def json(self):
            return payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    result = querido_diario.search_gazettes(["1302603"], terms=["cobrança extrajudicial"], max_pages=1)
    assert result["pages_read"] == 1
    assert len(result["records"]) == 1
    assert result["records"][0]["territory_id"] == "1302603"


def test_search_gazettes_requires_territory_ids():
    try:
        querido_diario.search_gazettes([])
    except ValueError as exc:
        assert "código IBGE" in str(exc)
    else:
        raise AssertionError("territory_ids vazio foi aceito")
