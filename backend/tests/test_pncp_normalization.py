from app.collectors.pncp import edital_url, merge_official, normalize_record, normalize_search_item, split_control

# Estruturas reais (campos abreviados) da API de consulta e do índice de busca.
OFFICIAL = {
    "numeroControlePNCP": "07977044000115-1-000095/2026", "anoCompra": 2026, "sequencialCompra": 95,
    "objetoCompra": "Contratação de serviços de cobrança extrajudicial",
    "orgaoEntidade": {"cnpj": "07977044000115", "razaoSocial": "MUNICIPIO DE MISSAO VELHA"},
    "unidadeOrgao": {"municipioNome": "Missão Velha", "ufSigla": "CE", "nomeUnidade": "PREFEITURA"},
    "modalidadeId": 8, "modalidadeNome": "Dispensa", "situacaoCompraNome": "Divulgada no PNCP",
    "dataPublicacaoPncp": "2026-11-06T13:22:13", "dataEncerramentoProposta": None,
    "valorTotalEstimado": 60432.0, "linkSistemaOrigem": "http://www.portaldemissaovelha.com.br",
}
SEARCH = {
    "numero_controle_pncp": "06988976000109-1-000008/2026", "orgao_cnpj": "06988976000109",
    "orgao_nome": "MUNICIPIO DE MAGALHAES DE ALMEIDA", "ano": "2026", "numero_sequencial": "8",
    "description": "recuperação de créditos previdenciários", "uf": "MA", "municipio_nome": "Magalhães de Almeida",
    "modalidade_licitacao_id": "9", "modalidade_licitacao_nome": "Inexigibilidade",
    "data_publicacao_pncp": "2026-01-26T17:49:40.551795", "data_fim_vigencia": None,
}


def test_normalize_official_record():
    i = normalize_record(OFFICIAL)
    assert i["company_name"] == "MUNICIPIO DE MISSAO VELHA" and i["cnpj"] == "07977044000115"
    assert (i["city"], i["state"]) == ("Missão Velha", "CE")
    assert i["url"] == "https://pncp.gov.br/app/editais/07977044000115/2026/95"
    assert i["origin_url"].startswith("http://www.portaldemissaovelha")
    assert i["estimated_value"] == 60432.0


def test_normalize_search_item_and_link():
    i = normalize_search_item(SEARCH)
    assert i["control"] == SEARCH["numero_controle_pncp"]
    assert i["url"] == "https://pncp.gov.br/app/editais/06988976000109/2026/8"
    assert i["modality_id"] == "9"


def test_split_control():
    assert split_control("06988976000109-1-000008/2026") == ("06988976000109", "2026", "8")
    assert split_control("invalido") == (None, None, None)


def test_merge_official_overrides_search_hint():
    found = normalize_search_item({**SEARCH, "data_fim_vigencia": "2026-12-01T09:00"})
    merged = merge_official(found, {**OFFICIAL, "dataEncerramentoProposta": "2026-11-20T10:00:00"})
    assert merged["deadline"] == "2026-11-20T10:00:00"
    assert merged["url"] == found["url"]
