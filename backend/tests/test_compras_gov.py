import httpx

from app.collectors import compras_gov


def test_normalize_contract_does_not_persist_supplier_document():
    item = compras_gov.normalize_contract({
        "codigoOrgao": 123,
        "nomeOrgao": "Órgão X",
        "numeroContrato": "10/2026",
        "objeto": "Serviços de cobrança extrajudicial",
        "informacoesComplementares": "Recuperação de créditos",
        "niFornecedor": "00000000000",
        "nomeRazaoSocialFornecedor": "Fornecedor PJ",
        "dataVigenciaInicial": "2026-01-01",
        "dataVigenciaFinal": "2026-12-31",
        "valorGlobal": 1000,
        "numeroControlePncpContrato": "ABC",
        "contratoExcluido": False,
    })
    assert item["org_code"] == "123"
    assert "supplier_name" not in item
    assert "niFornecedor" not in item
    assert "Fornecedor PJ" not in str(item)
    assert item["object"].startswith("Serviços de cobrança")


def test_search_contracts_filters_by_collection_terms(monkeypatch):
    payload = {
        "resultado": [
            {"codigoOrgao": 1, "nomeOrgao": "A", "objeto": "serviços de cobrança extrajudicial",
             "informacoesComplementares": "", "contratoExcluido": False},
            {"codigoOrgao": 1, "nomeOrgao": "A", "objeto": "manutenção predial",
             "informacoesComplementares": "", "contratoExcluido": False},
        ],
        "totalPaginas": 1,
        "totalRegistros": 2,
        "paginasRestantes": 0,
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
    result = compras_gov.search_contracts(["1"], "2026-01-01", "2026-12-31",
                                          terms=["cobrança extrajudicial"], max_pages=1)
    assert result["pages_read"] == 1
    assert len(result["records"]) == 1
    assert result["records"][0]["matched_terms"] == ["cobrança extrajudicial"]


def test_search_contracts_requires_org_code():
    try:
        compras_gov.search_contracts([], "2026-01-01", "2026-12-31")
    except ValueError as exc:
        assert "codigoOrgao" in str(exc)
    else:
        raise AssertionError("org_codes vazio foi aceito")


def test_capture_compras_gov_persists_only_buyer_signal(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.database import SessionLocal, ensure_schema
    from app.db.models import CaptureRun, Company, Opportunity

    ensure_schema()
    record = {
        "org_code": "123",
        "org_name": "Órgão Federal Teste",
        "management_unit": "Unidade Gestora Teste",
        "contract_number": "10/2026",
        "object": "Serviços de cobrança extrajudicial e recuperação de crédito.",
        "complement": "",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "value": 150000,
        "pncp_control": "CTRL-TESTE-123",
        "purchase_id": "COMPRA-1",
        "deleted": False,
        "source_url": compras_gov.ENDPOINT,
        "matched_terms": ["cobrança extrajudicial"],
        "relevance": "alta",
        "relevance_reason": "objeto de cobrança/recuperação",
    }
    monkeypatch.setattr(compras_gov, "search_contracts", lambda *args, **kwargs: {
        "records": [record], "pages_read": 1, "errors": [],
        "org_codes": ["123"], "date_from": "2026-01-01", "date_to": "2026-12-31",
    })
    try:
        with TestClient(app) as client:
            first = client.post("/api/capture/compras-gov", params={
                "org_codes": "123", "start_date": "2026-01-01", "end_date": "2026-12-31"
            })
            assert first.status_code == 200, first.text
            assert first.json()["created"] == 1
            second = client.post("/api/capture/compras-gov", params={
                "org_codes": "123", "start_date": "2026-01-01", "end_date": "2026-12-31"
            })
            assert second.status_code == 200
            assert second.json()["created"] == 0 and second.json()["updated"] == 1

        with SessionLocal() as db:
            opp = db.query(Opportunity).filter(
                Opportunity.source_name == "Compras.gov.br — contratos"
            ).one()
            assert opp.commercial_signal == "sinal_a_confirmar"
            assert opp.opportunity_class == "contrato_publico"
            assert opp.is_verified is False
            assert opp.company.name == "Órgão Federal Teste"
            assert "fornecedor" not in opp.evidence.casefold()
    finally:
        with SessionLocal() as db:
            opps = db.query(Opportunity).filter(
                Opportunity.source_name == "Compras.gov.br — contratos"
            ).all()
            company_ids = [o.company_id for o in opps]
            for o in opps:
                db.delete(o)
            db.flush()
            if company_ids:
                db.query(Company).filter(Company.id.in_(company_ids)).delete(synchronize_session=False)
            db.query(CaptureRun).filter(CaptureRun.source_name == "Compras.gov.br — contratos").delete()
            db.commit()


def test_capture_compras_gov_validates_dates_and_org_codes():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        assert client.post("/api/capture/compras-gov", params={
            "org_codes": "ABC", "start_date": "2026-01-01", "end_date": "2026-12-31"
        }).status_code == 400
        assert client.post("/api/capture/compras-gov", params={
            "org_codes": "123", "start_date": "2026-12-31", "end_date": "2026-01-01"
        }).status_code == 400
