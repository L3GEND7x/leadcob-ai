import httpx
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.database import SessionLocal, ensure_schema
from app.db.models import Company
from app.main import app
from app.services import compliance


def test_compliance_disabled_without_key(monkeypatch):
    monkeypatch.setattr(settings, "portal_transparencia_api_key", "")
    result = compliance.check_company("11222333000181")
    assert result["configured"] is False
    assert result["has_records"] is None
    assert result["records"] == []


def test_compliance_queries_ceis_and_cnep_without_exposing_key(monkeypatch):
    monkeypatch.setattr(settings, "portal_transparencia_api_key", "segredo-de-teste")
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["chave-api-dados"] == "segredo-de-teste"
        assert request.url.params["codigoSancionado"] == "11222333000181"
        source = "CEIS" if request.url.path.endswith("/ceis") else "CNEP"
        return httpx.Response(200, json=[{
            "id": 1 if source == "CEIS" else 2,
            "dataInicioSancao": "01/01/2026",
            "dataFimSancao": "31/12/2026",
            "tipoSancao": {"descricao": "Sanção teste"},
            "orgaoSancionador": {"nome": "Órgão teste"},
            "sancionado": {"nome": "EMPRESA TESTE LTDA"},
            "numeroProcesso": "PROC-1",
        }])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = compliance.check_company("11.222.333/0001-81", client=client)
    assert result["configured"] is True and result["has_records"] is True
    assert {x["source"] for x in result["records"]} == {"CEIS", "CNEP"}
    assert "segredo-de-teste" not in str(result)
    assert "inadimplência" in result["note"]


def test_company_compliance_route_uses_only_company_cnpj(monkeypatch):
    ensure_schema()
    with SessionLocal() as db:
        company = Company(name="COMPLIANCE TESTE LTDA", cnpj="11222333000181")
        db.add(company); db.commit(); cid = company.id
    monkeypatch.setattr(compliance, "check_company", lambda cnpj: {
        "configured": True, "cnpj": cnpj, "has_records": False, "records": [],
        "note": "Não é prova de inadimplência."
    })
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/companies/{cid}/compliance")
            assert response.status_code == 200
            assert response.json()["cnpj"] == "11222333000181"
    finally:
        with SessionLocal() as db:
            db.query(Company).filter_by(id=cid).delete()
            db.commit()
