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


def test_cnpj_lookup_enrich_and_prospects(monkeypatch):
    from app.collectors import cnpj_api
    from app.db.database import SessionLocal
    from app.db.models import Company

    data = {"cnpj": "05156977000116", "razao_social": "EXEMPLO FOMENTO LTDA", "nome_fantasia": "EXEMPLO",
            "cnae_principal": "6491300", "cnae_descricao": "Factoring", "cnaes_secundarios": [],
            "situacao_cadastral": "ATIVA", "porte": "DEMAIS", "natureza_juridica": "LTDA", "municipio": "MARINGA",
            "uf": "PR", "capital_social": 150000.0, "data_inicio_atividade": "2002-07-01", "matriz": True,
            "opcao_mei": False, "source": "BrasilAPI"}
    monkeypatch.setattr(cnpj_api, "lookup", lambda c: dict(data))
    with TestClient(app) as c:
        r = c.get("/api/cnpj/05156977000116").json()
        assert r["cnpj_formatted"] == "05.156.977/0001-16" and r["target_profile"] == "credito_fomento"
        db = SessionLocal(); comp = Company(name="Sem dados", cnpj="05156977000116"); db.add(comp); db.commit(); cid = comp.id; db.close()
        e = c.post(f"/api/companies/{cid}/enrich").json()
        assert e["name"] == "EXEMPLO FOMENTO LTDA" and e["target_profile"] == "credito_fomento" and e["company_size"] == "DEMAIS"
        assert any(p["id"] == cid for p in c.get("/api/prospects", params={"segment": "credito_fomento", "uf": "PR"}).json())
        assert c.get("/api/dashboard/summary").json()["prospects"] >= 1
        assert {s["key"] for s in c.get("/api/segments").json()} >= {"atacado", "credito_fomento"}

        def boom(_):
            raise cnpj_api.CNPJUnavailable("x")
        monkeypatch.setattr(cnpj_api, "lookup", boom)
        assert c.get("/api/cnpj/05156977000116").status_code == 502


def test_capture_jobs_flags_competitor_and_closes_missing(monkeypatch):
    from app.collectors import cnpj_api, jobboards
    from app.services.jobs import classify_job
    board = {"provider": "greenhouse", "token": "acme", "company_name": "Acme Cobranças"}
    def rec(i, title):
        return {**classify_job(title, location="São Paulo, SP"), "source_key": f"job:greenhouse:acme:{i}", "provider": "greenhouse",
                "board": board, "company_name": "Acme Cobranças", "cnpj": "11222333000181", "title": title,
                "location": "São Paulo, SP", "description": "x", "url": f"https://x/{i}", "published": None}
    first = {"records": [rec(1, "Analista de Cobrança"), rec(2, "Supervisor de Cobrança")], "boards_configured": 1,
             "boards_fetched": ["job:greenhouse:acme:"], "jobs_read": 2, "discarded_samples": [], "errors": []}
    monkeypatch.setattr(jobboards, "fetch_job_opportunities", lambda: first)
    monkeypatch.setattr(cnpj_api, "lookup", lambda c: {"cnpj": c, "razao_social": "ACME COBRANCAS LTDA", "cnae_principal": "8291100",
                                                         "cnae_descricao": "Atividades de cobranças", "source": "BrasilAPI"})
    with TestClient(app) as c:
        r = c.post("/api/capture/jobs").json()
        assert r["created"] == 2 and r["competitors"] == 2
        jobs = [o for o in c.get("/api/opportunities", params={"kind": "hiring"}).json() if o["source_key"] and o["source_key"].startswith("job:greenhouse:acme")]
        assert all(o["opportunity_class"] == "concorrente" and o["score"] == 0 for o in jobs)
        second = {**first, "records": [rec(1, "Analista de Cobrança")]}
        monkeypatch.setattr(jobboards, "fetch_job_opportunities", lambda: second)
        assert c.post("/api/capture/jobs").json()["closed"] == 1
        assert c.get("/api/prospects", params={"cnae": "8291"}).json() == []  # concorrentes fora da prospecção


def test_sources_catalog_is_consistent():
    import json, re
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    data = json.loads((root / "config" / "sources.json").read_text(encoding="utf-8"))
    doc = (root / "docs" / "fontes.md").read_text(encoding="utf-8")
    for s in data["sources"]:
        assert s["category"] in ("integrada", "consultada", "planejada")
        assert s["name"] in doc
        if s.get("url"):
            assert "utm_" not in s["url"]
        if s["category"] == "planejada":
            assert "NÃO conectada" in s["status"] or "manual" in s["status"]
    with TestClient(app) as c:
        r = c.get("/api/sources", params={"category": "integrada"}).json()
        assert r["sources"] and all(s["category"] == "integrada" for s in r["sources"])
        assert r["job_boards_configured"] >= 1


def test_market_datajud_snapshot(monkeypatch):
    from app.collectors import datajud
    fake = {"fonte": "DataJud", "tribunal": "TJRR", "uf": "RR", "periodo": {"inicio": "2025-11-01", "fim": "2026-11-09"},
            "total_processos": 10, "classes": [], "assuntos": [], "tipos_de_inadimplencia": [], "assuntos_nao_classificados": [],
            "municipios": [], "limites": []}
    monkeypatch.setattr(datajud, "market_map", lambda uf, months: dict(fake))
    with TestClient(app) as c:
        assert c.get("/api/market/datajud", params={"uf": "RR"}).status_code == 404
        assert c.post("/api/market/datajud", params={"uf": "RR"}).json()["total_processos"] == 10
        assert c.get("/api/market/datajud", params={"uf": "RR"}).json()["tribunal"] == "TJRR"
        assert any(d["key"] == "mensalidades" for d in c.get("/api/debt-types").json())
