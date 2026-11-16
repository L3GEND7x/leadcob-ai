import pytest

from app.collectors import ans_profile


def test_ans_profile_discards_contacts_and_representatives():
    content = (
        "Registro_ANS;CNPJ;Razao_Social;Nome_Fantasia;Modalidade;Cidade;UF;Data_Registro_ANS;"
        "Telefone;Endereco_eletronico;Representante;Cargo_Representante\n"
        "123456;12.345.678/0001-90;OPERADORA TESTE LTDA;TESTE SAUDE;Medicina de Grupo;Manaus;AM;1998-12-22;"
        "92999999999;pessoa@example.com;NOME DE PESSOA;DIRETOR\n"
    ).encode("utf-8")
    rows = ans_profile.parse_csv(content)
    assert rows == [{
        "cnpj": "12345678000190",
        "name": "OPERADORA TESTE LTDA",
        "trade_name": "TESTE SAUDE",
        "ans_registry": "123456",
        "modality": "Medicina de Grupo",
        "city": "Manaus",
        "state": "AM",
        "registered_at": "1998-12-22",
        "profile_key": "planos_seguros",
        "source_name": "ANS — Operadoras ativas",
        "source_url": ans_profile.URL,
    }]
    serialized = str(rows)
    assert "92999999999" not in serialized
    assert "pessoa@example.com" not in serialized
    assert "NOME DE PESSOA" not in serialized


def test_ans_profile_rejects_unexpected_header():
    with pytest.raises(ValueError, match="Formato ANS inesperado"):
        ans_profile.parse_csv(b"outra;coisa\n1;2\n")


def test_ans_profile_decodes_latin1():
    content = (
        "Registro_ANS;CNPJ;Razao_Social;Modalidade\n"
        "123456;12345678000190;OPERADORA SAUDE;Autogestão\n"
    ).encode("latin-1")
    assert ans_profile.parse_csv(content)[0]["modality"] == "Autogestão"
