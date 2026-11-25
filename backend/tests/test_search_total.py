"""Busca ordenada por pontuação: o total exibido é o real do filtro, não a amostra pontuada."""
from fastapi.testclient import TestClient

import app.api.routes_crm as routes_crm
from app.main import app
from app.db.database import ensure_schema
from tests.test_crm import make_company

ensure_schema()


def test_score_sort_reports_real_total_and_how_many_were_ranked(monkeypatch):
    marker = "TOTAL REAL AMOSTRA"
    for i in range(5):
        make_company(name=f"{marker} {i} LTDA", capital_social=1_000_000.0 + i)
    monkeypatch.setattr(routes_crm, "CANDIDATE_LIMIT", 3)
    with TestClient(app) as c:
        d = c.get("/api/companies/search", params={"q": marker, "sort": "score", "per_page": 2}).json()
        assert d["total"] == 5            # antes: devolvia 3 (a amostra) como se fosse a base inteira
        assert d["scored"] == 3 and d["partial"] is True
        assert "as 3 empresas de maior capital" in d["note"] and "município, perfil, CNAE" in d["note"]
        names = {x["name"] for x in d["items"]}
        assert all(marker in n for n in names)
        d2 = c.get("/api/companies/search", params={"q": marker, "sort": "name", "per_page": 2}).json()
        assert d2["total"] == 5 and d2["note"] is None   # outras ordenações percorrem todas
        d3 = c.get("/api/companies/search", params={"q": marker, "sort": "score", "per_page": 10}).json()
        assert d3["partial"] is True and len(d3["items"]) == 3


def test_score_sort_without_cap_is_not_partial():
    marker = "TOTAL REAL SEM CORTE"
    for i in range(2):
        make_company(name=f"{marker} {i} LTDA")
    with TestClient(app) as c:
        d = c.get("/api/companies/search", params={"q": marker, "sort": "score"}).json()
        assert d["total"] == 2 and d["scored"] == 2 and d["partial"] is False and d["note"] is None
