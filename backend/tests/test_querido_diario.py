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


def test_capture_querido_diario_persists_signal_without_claiming_proven(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.database import SessionLocal, ensure_schema
    from app.db.models import CaptureRun, Company, Opportunity

    ensure_schema()
    record = {
        "company_name": "Município de Manaus",
        "city": "Manaus",
        "state": "AM",
        "territory_id": "1302603",
        "published": "2026-11-10",
        "url": "https://example.org/diario.pdf",
        "object": "Contratação de serviços de cobrança extrajudicial.",
        "title": "Contratação de serviços de cobrança extrajudicial.",
        "relevance": "alta",
        "relevance_reason": "objeto de cobrança/recuperação",
        "opportunity_class": "prazo_nao_informado",
        "class_reason": "prazo de propostas não informado — conferir no edital",
        "evidence_level": "fonte_primaria_diario",
        "commercial_signal": "sinal_a_confirmar",
        "matched_terms": ["cobrança extrajudicial"],
        "estimated_value": None,
        "modality_id": None,
    }
    monkeypatch.setattr(querido_diario, "search_gazettes", lambda *args, **kwargs: {
        "records": [record], "pages_read": 1, "errors": [],
        "terms": ["cobrança extrajudicial"], "territory_ids": ["1302603"],
    })

    try:
        with TestClient(app) as client:
            first = client.post("/api/capture/querido-diario", params={
                "territory_ids": "1302603", "querystring": "cobrança extrajudicial"
            })
            assert first.status_code == 200, first.text
            assert first.json()["created"] == 1
            second = client.post("/api/capture/querido-diario", params={
                "territory_ids": "1302603", "querystring": "cobrança extrajudicial"
            })
            assert second.status_code == 200
            assert second.json()["created"] == 0 and second.json()["updated"] == 1

        with SessionLocal() as db:
            opp = db.query(Opportunity).filter(
                Opportunity.source_name == "Querido Diário — diário oficial municipal"
            ).one()
            assert opp.commercial_signal == "sinal_a_confirmar"
            assert opp.is_verified is False
            assert opp.company.segment == "Órgão público"
            assert "não informado" in opp.evidence or "Trecho:" in opp.evidence
    finally:
        with SessionLocal() as db:
            ids = [x.id for x in db.query(Opportunity).filter(
                Opportunity.source_name == "Querido Diário — diário oficial municipal"
            ).all()]
            if ids:
                company_ids = [x.company_id for x in db.query(Opportunity).filter(Opportunity.id.in_(ids)).all()]
                db.query(Opportunity).filter(Opportunity.id.in_(ids)).delete(synchronize_session=False)
                db.query(Company).filter(Company.id.in_(company_ids)).delete(synchronize_session=False)
            db.query(CaptureRun).filter(CaptureRun.source_name == "Querido Diário — diários municipais").delete()
            db.commit()


def test_capture_querido_diario_validates_ibge_code():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        assert client.post("/api/capture/querido-diario", params={"territory_ids": "13A2603"}).status_code == 400


def test_invalid_gazette_payloads_are_not_counted_as_success(monkeypatch):
    for payload in ({}, {"gazettes": None}, {"gazettes": {}}, {"gazettes": [None]},
                    {"gazettes": [], "total_gazettes": "invalid"}):
        monkeypatch.setattr(querido_diario, "request_json", lambda *a, **kw: payload)
        result = querido_diario.search_gazettes(["1302603"], terms=["cobrança"], pause=0)
        assert result["pages_read"] == 0
        assert result["records"] == []
        assert len(result["errors"]) == 1


def test_valid_empty_gazette_payload_is_success(monkeypatch):
    monkeypatch.setattr(querido_diario, "request_json",
                        lambda *a, **kw: {"gazettes": [], "total_gazettes": 0})
    result = querido_diario.search_gazettes(["1302603"], terms=["cobrança"], pause=0)
    assert result["pages_read"] == 1
    assert result["records"] == []
    assert result["errors"] == []
