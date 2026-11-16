import httpx
import pytest

from app.collectors import cvm_profile


def test_cvm_profile_parses_only_corporate_registry_fields():
    content = (
        "CNPJ_CIA;DENOM_SOCIAL;SIT;CD_CVM;EMAIL_RESP;TEL_RESP\n"
        "12.345.678/0001-90;COMPANHIA TESTE S.A.;ATIVO;12345;pessoa@example.com;11999999999\n"
    ).encode("latin-1")
    rows = cvm_profile.parse_csv(content)
    assert rows == [{
        "cnpj": "12345678000190",
        "name": "COMPANHIA TESTE S.A.",
        "registry_status": "ATIVO",
        "cvm_code": "12345",
        "profile_key": "companhia_aberta",
        "source_name": "CVM — Companhias Abertas",
        "source_url": cvm_profile.URL,
    }]
    assert "pessoa@example.com" not in str(rows)
    assert "11999999999" not in str(rows)


def test_cvm_profile_rejects_unexpected_header():
    with pytest.raises(ValueError, match="Formato CVM inesperado"):
        cvm_profile.parse_csv(b"outra;coisa\n1;2\n")


def test_cvm_profile_fetch_uses_official_csv(monkeypatch):
    payload = "CNPJ_CIA;DENOM_SOCIAL;SIT\n12345678000190;CIA TESTE;ATIVO\n".encode("latin-1")

    class FakeResponse:
        content = payload
        def raise_for_status(self):
            return None

    class FakeClient:
        def get(self, url):
            assert url == cvm_profile.URL
            return FakeResponse()

    rows = cvm_profile.fetch(client=FakeClient())
    assert rows[0]["profile_key"] == "companhia_aberta"
