from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.collectors import pncp
from app.main import app
from app.services.procurement import classify

NOW = datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc)


def rec(control, obj, deadline="2027-01-10T10:00:00", evidence="confirmada_api_oficial", modality="6"):
    cnpj = control[:14]
    item = {"company_name": "ORGAO " + cnpj, "cnpj": cnpj, "city": "Manaus", "state": "AM", "object": obj, "complement": "",
            "title": obj, "control": control, "year": "2026", "sequential": "1", "modality_id": modality,
            "modality_name": "Pregão - Eletrônico", "situation": "Divulgada no PNCP", "published": "2026-11-01",
            "deadline": deadline, "estimated_value": 150000.0, "origin_url": None,
            "url": f"https://pncp.gov.br/app/editais/{cnpj}/2026/1", "evidence_level": evidence, "matched_terms": ["x"]}
    item.update(classify(item, NOW))
    return item


def fake_batch(**_):
    return {"records": [
        rec("11111111000111-1-000001/2026", "serviços de cobrança extrajudicial"),
        rec("22222222000122-1-000001/2026", "recuperação de créditos previdenciários (assessoria tributária)"),
        rec("33333333000133-1-000001/2026", "cobrança automática de pedágios"),
    ], "pages_read": 3, "confirmed": 3, "errors": []}


def test_health_and_summary():
    with TestClient(app) as c:
        assert c.get("/api/health").json()["status"] == "ok"
        s = c.get("/api/dashboard/summary").json()
        assert {"proven", "to_confirm", "open_procurements"} <= s.keys()


def test_capture_classifies_stores_and_deduplicates(monkeypatch):
    monkeypatch.setattr(pncp, "search_opportunities", fake_batch)
    with TestClient(app) as c:
        r = c.post("/api/capture/pncp").json()
        assert (r["created"], r["discarded"], r["proven"], r["to_confirm"]) == (2, 1, 1, 1)
        assert r["discarded_samples"][0]["objeto"].startswith("cobrança automática")
        again = c.post("/api/capture/pncp").json()
        assert again["created"] == 0 and again["updated"] == 2
        proven = c.get("/api/opportunities", params={"signal": "oportunidade_comprovada"}).json()
        assert len(proven) == 1 and proven[0]["relevance"] == "alta" and proven[0]["deadline"]
        assert "Aderência: alta" in proven[0]["evidence"]
        # agentes não podem rebaixar/alterar a pontuação do edital
        before = proven[0]["score"]
        after = c.post(f"/api/agents/run/{proven[0]['id']}").json()
        assert after["opportunity"]["score"] == before and after["opportunity"]["status"] == "qualified"
        runs = c.get("/api/capture/runs").json()
        assert runs[0]["status"] == "completed"


def test_capture_total_failure_returns_502(monkeypatch):
    monkeypatch.setattr(pncp, "search_opportunities", lambda **_: {"records": [], "pages_read": 0, "confirmed": 0, "errors": ["RemoteProtocolError"]})
    with TestClient(app) as c:
        assert c.post("/api/capture/pncp").status_code == 502
        assert c.get("/api/capture/runs").json()[0]["status"] == "failed"


def test_record_reclassified_as_discard_leaves_dashboard(monkeypatch):
    first = rec("44444444000144-1-000001/2026", "serviços de cobrança extrajudicial")
    monkeypatch.setattr(pncp, "search_opportunities", lambda **_: {"records": [first], "pages_read": 1, "confirmed": 1, "errors": []})
    with TestClient(app) as c:
        c.post("/api/capture/pncp")
        before = c.get("/api/dashboard/summary").json()["proven"]
        later = rec("44444444000144-1-000001/2026", "leitura informatizada de hidrômetros e entrega de faturas")
        monkeypatch.setattr(pncp, "search_opportunities", lambda **_: {"records": [later], "pages_read": 1, "confirmed": 1, "errors": []})
        c.post("/api/capture/pncp")
        assert c.get("/api/dashboard/summary").json()["proven"] == before - 1
        assert len(c.get("/api/opportunities", params={"status": "discarded"}).json()) >= 1
