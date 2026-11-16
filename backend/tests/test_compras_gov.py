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
    assert item["supplier_name"] == "Fornecedor PJ"
    assert "niFornecedor" not in item
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
