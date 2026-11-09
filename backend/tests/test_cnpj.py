import httpx
import pytest

from app.collectors import cnpj_api
from app.services.cnpj import format_cnpj, is_valid_cnpj, normalize_api


@pytest.mark.parametrize("cnpj,ok", [
    ("51.213.049/0001-63", True), ("07977044000115", True), ("00000000000191", True),
    ("12.ABC.345/01DE-35", True),   # exemplo oficial de CNPJ alfanumérico (Receita Federal)
    ("12ABC34501DE36", False), ("11111111111111", False), ("123", False), ("", False),
])
def test_cnpj_validation(cnpj, ok):
    assert is_valid_cnpj(cnpj) is ok


def test_format():
    assert format_cnpj("51213049000163") == "51.213.049/0001-63"


PAYLOAD = {  # esquema real da BrasilAPI/Minha Receita, valores fictícios
    "cnpj": "05156977000116", "razao_social": "EXEMPLO FOMENTO MERCANTIL LTDA", "nome_fantasia": "EXEMPLO",
    "cnae_fiscal": 6491300, "cnae_fiscal_descricao": "Sociedades de fomento mercantil - factoring",
    "cnaes_secundarios": [{"codigo": 6619399, "descricao": "x"}], "descricao_situacao_cadastral": "ATIVA",
    "porte": "DEMAIS", "natureza_juridica": "Sociedade Empresária Limitada", "municipio": "MARINGA", "uf": "PR",
    "capital_social": 150000, "data_inicio_atividade": "2002-07-01", "identificador_matriz_filial": 1,
    "opcao_pelo_mei": False,
    # dados pessoais que NÃO podem ser guardados
    "qsa": [{"nome_socio": "FULANO DE TAL", "cnpj_cpf_do_socio": "***123456**"}],
    "email": "fulano@contabilidade.com.br", "ddd_telefone_1": "4433334444", "logradouro": "RUA X", "numero": "10",
}


def test_normalize_keeps_only_company_data():
    d = normalize_api(PAYLOAD, "BrasilAPI")
    assert d["cnae_principal"] == "6491300" and d["cnaes_secundarios"] == ["6619399"] and d["matriz"] is True
    assert d["capital_social"] == 150000.0
    flat = str(d)
    for leaked in ("FULANO", "contabilidade", "4433334444", "RUA X"):
        assert leaked not in flat


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_lookup_falls_back_to_minhareceita(monkeypatch):
    monkeypatch.setattr(cnpj_api.time, "sleep", lambda *_: None)
    calls = []
    def handler(req):
        calls.append(req.url.host)
        if req.url.host == "brasilapi.com.br":
            return httpx.Response(503)
        return httpx.Response(200, json=PAYLOAD)
    d = cnpj_api.lookup("05156977000116", http=client(handler))
    assert d["source"] == "Minha Receita" and "brasilapi.com.br" in calls


def test_lookup_not_found_and_invalid():
    with pytest.raises(cnpj_api.CNPJNotFound):
        cnpj_api.lookup("05156977000116", http=client(lambda r: httpx.Response(404, json={"message": "x"})))
    with pytest.raises(cnpj_api.CNPJInvalid):  # nem chega à rede
        cnpj_api.lookup("11111111111111", http=client(lambda r: (_ for _ in ()).throw(AssertionError("rede"))))


@pytest.mark.parametrize("cnae,expected", [
    ("4623199", "atacado"), ("4687701", "atacado"), ("4644301", "atacado"),
    # representantes (46.1): continuam na base, com perfil próprio (prioridade baixa) — não são "atacado"
    ("4611700", "representacao_comercial"), ("4619200", "representacao_comercial"),
    ("4711302", "varejo"), ("4781400", "varejo"),          # varejo entra: do pequeno ao grande
    ("8513900", "educacao_privada"), ("8112500", "condominios"), ("6550200", "planos_seguros"),
    ("9313100", "academias_clubes"), ("4511101", "concessionarias_veiculos"), ("6491300", "credito_fomento"),
    ("8291100", "concorrente_cobranca"), ("8411600", "setor_publico"),
    ("9700500", None), ("9900800", None),                   # serviços domésticos e organismos internacionais
])
def test_segment_profiles(cnae, expected):
    from app.services.segments import profile_for
    assert profile_for(cnae) == expected


def test_every_cnae_division_has_a_profile():
    """Nenhum setor fica de fora: toda divisão da CNAE (01–96) recebe perfil."""
    from app.services.segments import profile_for
    divisions = [f"{d:02d}" for d in range(1, 97)]
    missing = [d for d in divisions if profile_for(d + "00000") is None]
    assert missing == []


def test_wanted_filter_still_restricts():
    from app.services.segments import profile_for
    assert profile_for("4711302", ["atacado"]) is None and profile_for("4623199", ["atacado"]) == "atacado"


def test_debt_types_for_profiles():
    from app.services.segments import SEGMENTS, DEBT_TYPES, debt_types_for
    assert [d["key"] for d in debt_types_for("condominios")] == ["aluguel_condominio"]
    for key, seg in SEGMENTS.items():
        assert all(t in DEBT_TYPES for t in seg["debt_types"]), key
