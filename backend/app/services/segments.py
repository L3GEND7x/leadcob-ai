"""Setores e tipos de inadimplência — TODA empresa com recebíveis é potencial cliente.

Desde a v0.4 os perfis são RÓTULOS de priorização, não filtro de entrada: qualquer
empresa ativa de qualquer setor e porte entra na base (do pequeno varejista ao grande
grupo). Os perfis dizem qual inadimplência é típica do setor, o que orienta abordagem
e cruzamento com o mapa do DataJud.

Continua sendo HIPÓTESE COMERCIAL: estar num setor não comprova inadimplência.
Ordem importa: o primeiro prefixo que casar vence (mais específico primeiro).
Códigos = prefixos do CNAE de 7 dígitos (subclasse IBGE).
"""

# Tipos de inadimplência. `datajud_assuntos` = nomes de assuntos OBSERVADOS no DataJud
# (TJAM, 11/2025–10/2026) dentro das classes de cobrança. Cada assunto pertence a UM único
# tipo (listas disjuntas, verificado em teste) para não contar o mesmo processo duas vezes.
# Assuntos genéricos ("Pagamento", "Compra e Venda", "Execução Contratual", "Perdas e Danos"...)
# ficam como "não classificados". Lista vazia = nenhum assunto específico observado ainda.
DEBT_TYPES = {
    "financiamento_garantia": {"label": "Financiamentos com garantia (alienação fiduciária)",
                               "datajud_assuntos": ["Alienação Fiduciária", "Busca e Apreensão"]},
    "credito_bancario": {"label": "Crédito bancário, cartão e empréstimos",
                         "datajud_assuntos": ["Contratos Bancários", "Cédula de Crédito Bancário"]},
    "crediario_varejo": {"label": "Notas promissórias, cheques e crediário",
                         "datajud_assuntos": ["Nota Promissória"]},
    "duplicatas_b2b": {"label": "Duplicatas e boletos entre empresas (B2B)", "datajud_assuntos": ["Duplicata"]},
    "aluguel_condominio": {"label": "Aluguéis e taxas condominiais",
                           "datajud_assuntos": ["Despesas Condominiais", "Cobrança de Aluguéis - Sem despejo",
                                                "Condomínio", "Locação de Móvel"]},
    "mensalidades": {"label": "Mensalidades e assinaturas recorrentes", "datajud_assuntos": ["Mensalidades"]},
    "servicos_prestados": {"label": "Serviços prestados e honorários", "datajud_assuntos": ["Prestação de Serviços"]},
    "seguros_planos": {"label": "Prêmios de seguro e planos de saúde", "datajud_assuntos": ["Seguro"]},
    "imoveis_parcelados": {"label": "Imóveis e lotes vendidos a prazo", "datajud_assuntos": ["Compromisso"]},
    "faturas_consumo": {"label": "Faturas de consumo (energia, água, telecom)", "datajud_assuntos": []},
    "divida_ativa": {"label": "Dívida ativa (tributos e taxas públicas)", "datajud_assuntos": [],
                     "datajud_classes": [1116]},
    "contribuicoes_associativas": {"label": "Contribuições e mensalidades associativas", "datajud_assuntos": []},
}

SEGMENTS = {
    # --- específicos (4+ dígitos) ---
    "concorrente_cobranca": {"label": "Empresas de cobrança (concorrentes)", "cnae_prefixes": ["8291"],
                             "debt_types": [], "rationale": "CNAE 8291-1/00: concorrente, não cliente."},
    "condominios": {"label": "Condomínios prediais", "cnae_prefixes": ["8112"],
                    "debt_types": ["aluguel_condominio"], "rationale": "Taxas condominiais em atraso."},
    "imobiliario_condominios": {"label": "Imobiliárias e administração de imóveis", "cnae_prefixes": ["68"],
                                "debt_types": ["aluguel_condominio", "imoveis_parcelados"],
                                "rationale": "Aluguéis, condomínios administrados e vendas a prazo."},
    "credito_fomento": {"label": "Fomento mercantil, crédito e financeiras",
                        "cnae_prefixes": ["6491", "6492", "6493", "6436", "6437"],
                        "debt_types": ["credito_bancario", "duplicatas_b2b", "financiamento_garantia"],
                        "rationale": "Atividade-fim é crédito."},
    "planos_seguros": {"label": "Seguros, planos de saúde e previdência", "cnae_prefixes": ["65"],
                       "debt_types": ["seguros_planos"], "rationale": "Prêmios e mensalidades em atraso."},
    "financeiro": {"label": "Bancos, cooperativas de crédito e serviços financeiros", "cnae_prefixes": ["64", "66"],
                   "debt_types": ["credito_bancario", "financiamento_garantia"], "rationale": "Carteiras de crédito."},
    "academias_clubes": {"label": "Academias, clubes e atividades esportivas", "cnae_prefixes": ["931"],
                         "debt_types": ["mensalidades"], "rationale": "Mensalidades recorrentes."},
    "telecom_provedores": {"label": "Telecomunicações e provedores de internet", "cnae_prefixes": ["61"],
                           "debt_types": ["faturas_consumo", "mensalidades"], "rationale": "Assinantes inadimplentes."},
    "concessionarias_veiculos": {"label": "Veículos: concessionárias, revendas e oficinas", "cnae_prefixes": ["45"],
                                 "debt_types": ["financiamento_garantia", "crediario_varejo", "servicos_prestados"],
                                 "rationale": "Vendas financiadas e serviços a prazo."},
    "representacao_comercial": {"label": "Representantes comerciais e agentes do comércio", "cnae_prefixes": ["461"],
                                "debt_types": ["servicos_prestados"],
                                "rationale": "Comissões a receber; carteira própria pequena (prioridade baixa)."},
    "atacado": {"label": "Comércio atacadista e distribuição",
                "cnae_prefixes": ["462", "463", "464", "465", "466", "467", "468", "469"],
                "debt_types": ["duplicatas_b2b"], "rationale": "Vendas B2B a prazo."},
    "varejo": {"label": "Comércio varejista (do pequeno ao grande)", "cnae_prefixes": ["47"],
               "debt_types": ["crediario_varejo", "duplicatas_b2b"], "rationale": "Crediário, cheques, carnês e cartão próprio."},
    "educacao_privada": {"label": "Educação privada", "cnae_prefixes": ["85"],
                         "debt_types": ["mensalidades"], "rationale": "Mensalidades escolares e universitárias."},
    "saude_privada": {"label": "Saúde e assistência social", "cnae_prefixes": ["86", "87", "88"],
                      "debt_types": ["servicos_prestados", "mensalidades"], "rationale": "Particulares, convênios, glosas."},
    "utilidades": {"label": "Energia, gás, água, saneamento e resíduos", "cnae_prefixes": ["35", "36", "37", "38", "39"],
                   "debt_types": ["faturas_consumo"], "rationale": "Faturas de consumo em larga escala."},
    "construcao": {"label": "Construção e incorporação", "cnae_prefixes": ["41", "42", "43"],
                   "debt_types": ["imoveis_parcelados", "servicos_prestados", "duplicatas_b2b"],
                   "rationale": "Unidades vendidas a prazo e serviços B2B."},
    "industria": {"label": "Indústria (extrativa e de transformação)",
                  "cnae_prefixes": [f"{i:02d}" for i in range(5, 34)],
                  "debt_types": ["duplicatas_b2b"], "rationale": "Faturamento a prazo para revendas."},
    "agro": {"label": "Agropecuária, pesca e florestal", "cnae_prefixes": ["01", "02", "03"],
             "debt_types": ["duplicatas_b2b", "financiamento_garantia"], "rationale": "Vendas e insumos a prazo, safra."},
    "transporte_logistica": {"label": "Transporte, armazenagem e correio", "cnae_prefixes": ["49", "50", "51", "52", "53"],
                             "debt_types": ["servicos_prestados", "duplicatas_b2b"], "rationale": "Fretes faturados a prazo."},
    "hospedagem_alimentacao": {"label": "Hotéis, bares, restaurantes e eventos", "cnae_prefixes": ["55", "56"],
                               "debt_types": ["servicos_prestados"], "rationale": "Eventos e contas corporativas."},
    "tecnologia_midia": {"label": "Software, TI, mídia e comunicação", "cnae_prefixes": ["58", "59", "60", "62", "63"],
                         "debt_types": ["mensalidades", "servicos_prestados"], "rationale": "Assinaturas e contratos."},
    "servicos_profissionais": {"label": "Serviços profissionais (contábeis, jurídicos, engenharia, publicidade)",
                               "cnae_prefixes": ["69", "70", "71", "72", "73", "74", "75"],
                               "debt_types": ["servicos_prestados"], "rationale": "Honorários a receber."},
    "servicos_empresariais": {"label": "Locação, segurança, limpeza, agências e apoio administrativo",
                              "cnae_prefixes": ["77", "78", "79", "80", "81", "82"],
                              "debt_types": ["servicos_prestados", "duplicatas_b2b"], "rationale": "Contratos B2B."},
    "setor_publico": {"label": "Administração pública", "cnae_prefixes": ["84"],
                      "debt_types": ["divida_ativa"], "rationale": "Dívida ativa; contratação por licitação (ver PNCP)."},
    "cultura_lazer": {"label": "Artes, cultura e recreação", "cnae_prefixes": ["90", "91", "92", "93"],
                      "debt_types": ["mensalidades", "servicos_prestados"], "rationale": "Mensalidades e ingressos."},
    "associacoes": {"label": "Associações, sindicatos e entidades", "cnae_prefixes": ["94"],
                    "debt_types": ["contribuicoes_associativas"], "rationale": "Contribuições em atraso."},
    "servicos_pessoais": {"label": "Reparação e serviços pessoais", "cnae_prefixes": ["95", "96"],
                          "debt_types": ["servicos_prestados", "mensalidades"], "rationale": "Serviços a prazo."},
}

# Divisões sem sentido comercial para cobrança: serviços domésticos (empregador pessoa física)
# e organismos internacionais.
EXCLUDED_PREFIXES = ["97", "99"]
FALLBACK_PROFILE = "demais_setores"
SEGMENTS[FALLBACK_PROFILE] = {"label": "Demais setores", "cnae_prefixes": [], "debt_types": ["duplicatas_b2b", "servicos_prestados"],
                              "rationale": "Qualquer empresa ativa com recebíveis."}

# Natureza jurídica 213-5 (empresário individual, inclui MEI): na amostra real de 09/11/2026,
# 70% dessas razões sociais eram NOME DA PESSOA + CPF. Exige decisão sobre base legal.
INDIVIDUAL_NATURE = "2135"


def is_excluded(cnae: str | None) -> bool:
    return bool(cnae) and any(cnae.startswith(p) for p in EXCLUDED_PREFIXES)


def profile_for(cnae: str | None, wanted: list[str] | None = None) -> str | None:
    """Perfil do CNAE. Sem `wanted`, toda empresa recebe um perfil (fallback: demais setores).
    Com `wanted`, devolve None quando o perfil não está na lista."""
    if not cnae or is_excluded(cnae):
        return None
    found = FALLBACK_PROFILE
    for key, seg in SEGMENTS.items():
        if any(cnae.startswith(p) for p in seg["cnae_prefixes"]):
            found = key
            break
    if wanted and found not in wanted:
        return None
    return found


def debt_types_for(profile: str | None) -> list[dict]:
    seg = SEGMENTS.get(profile or "")
    return [{"key": k, **DEBT_TYPES[k]} for k in (seg or {}).get("debt_types", []) if k in DEBT_TYPES]
