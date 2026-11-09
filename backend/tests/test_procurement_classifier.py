"""Casos extraídos de objetos reais publicados no PNCP (consulta de 09/11/2026)."""
from datetime import datetime, timezone

import pytest

from app.services.procurement import classify, parse_dt, relevance_of, score_procurement

NOW = datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("obj,expected", [
    ("credenciamento de empresas especializadas para prestação de serviços de cobrança extrajudicial, em conformidade com as necessidades", "alta"),
    ("Contratação de empresa especializada em cobrança amigável e extrajudicial de créditos inadimplidos da autarquia", "alta"),
    ("Contratação de empresa para cobrança administrativa da dívida ativa tributária do município", "alta"),
    # Recuperação de créditos tributários por assessoria/advocacia: outro mercado
    ("Contratação de pessoa jurídica especializada em diagnóstico e recuperação de créditos financeiros e econômicos referentes as rubricas previdenciárias e ao imposto sobre serviços de qualquer natureza (ISSQN)", "revisar"),
    ("CONTRATAÇÃO DE SOCIEDADE DE ADVOGADOS PARA ... RECUPERAÇÃO DE CRÉDITOS E RECEITAS MUNICIPAIS REFERENTES AO FUNDO DE PARTICIPAÇÃO DOS MUNICÍPIOS FPM", "revisar"),
    ("PRESTAÇÃO DE SERVIÇOS DE ASSESSORIA E AUDITORIA TRIBUTARIA COM A FINALIDADE DE RECUPERAÇÃO DE CREDITO, ACOMPANHADO DE SISTEMA DE ISS ELETRÔNICO", "revisar"),
    # Falsos positivos reais da busca textual
    ("Contratação de empresa na prestação de serviços de cobrança automática de pedágios em rodovias", "descartar"),
    ("CONTRATAÇÃO DE INSTITUIÇÃO FINANCEIRA PARA PRESTAÇÃO DE SERVIÇOS BANCÁRIOS DE ARRECADAÇÃO, EMISSÃO E PROCESSAMENTO de cobrança", "descartar"),
    ("Prestação de serviços gráficos especializados para produção de documentos destinados às atividades de faturamento, cobrança administrativa", "descartar"),
    ("CONTRATAÇÃO DE EMPRESA ESPECIALIZADA PARA PRESTAÇÃO DE SERVIÇOS DE LOCAÇÃO DE DECORAÇÃO NATALINA ILUMINADA", "descartar"),
    ("SERVIÇO DE TERCEIRO - PJ", "descartar"),
    # Falso positivo real que a primeira versão do classificador marcou como "alta"
    ("CONTRATAÇÃO DE EMPRESA ESPECIALIZADA ... PARA SERVIÇOS DE LEITURA INFORMATIZADA DE HIDRÔMETROS, EMISSÃO E ENTREGA SIMULTÂNEA DE FATURAS DE ÁGUA/ESGOTO, ENTREGA DE AVISOS DE INADIMPLÊNCIA", "descartar"),
    # Termo fraco isolado: revisar, nunca alta
    ("Contratação de serviços de apoio administrativo, incluindo controle de inadimplência de permissionários", "revisar"),
    ("", "descartar"),
])
def test_relevance_real_objects(obj, expected):
    assert relevance_of(obj)[0] == expected


def item(**kw):
    base = {"object": "serviços de cobrança extrajudicial", "modality_id": 12, "deadline": "2027-08-04T09:59",
            "evidence_level": "confirmada_api_oficial", "estimated_value": None}
    base.update(kw)
    return base


def test_proven_requires_open_relevant_and_confirmed():
    assert classify(item(), NOW)["commercial_signal"] == "oportunidade_comprovada"
    assert classify(item(evidence_level="indicio_busca"), NOW)["commercial_signal"] == "sinal_a_confirmar"
    assert classify(item(deadline="2026-11-01T09:00"), NOW)["opportunity_class"] == "edital_encerrado"
    assert classify(item(object="recuperação de créditos previdenciários"), NOW)["commercial_signal"] == "sinal_a_confirmar"


def test_inexigibility_is_market_signal_not_biddable():
    r = classify(item(modality_id="9", deadline=None), NOW)
    assert r["opportunity_class"] == "contratacao_direta"
    assert r["commercial_signal"] == "sinal_a_confirmar"


def test_deadline_uses_brasilia_time():
    # 10:30 BRT = 13:30 UTC: já encerrado às 14:00 UTC
    assert classify(item(deadline="2026-11-09T10:30:00"), NOW)["opportunity_class"] == "edital_encerrado"
    assert classify(item(deadline="2026-11-09T11:30:00"), NOW)["opportunity_class"] == "edital_aberto"


def test_parse_dt_handles_nanoseconds_and_missing():
    assert parse_dt("2026-11-06T13:22:13.468769959").year == 2026
    assert parse_dt(None) is None and parse_dt("lixo") is None


def test_score_orders_proven_above_signals():
    proven = item(); proven.update(classify(proven, NOW))
    weak = item(evidence_level="indicio_busca", deadline=None, modality_id="9", object="recuperação de créditos tributários")
    weak.update(classify(weak, NOW))
    assert score_procurement(proven)[0] > score_procurement(weak)[0]
