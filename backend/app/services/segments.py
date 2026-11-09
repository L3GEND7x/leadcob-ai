"""Perfis de segmento para a base de empresas-alvo (prospecção por CNAE).

São HIPÓTESES COMERCIAIS, não sinais de demanda: estar num CNAE só indica que a
empresa se parece com o perfil de quem costuma ter carteira de recebíveis.
Ajuste a lista conforme o histórico real de clientes do escritório/empresa.
Códigos = prefixos do CNAE de 7 dígitos (subclasse IBGE).
"""
SEGMENTS = {
    "atacado": {
        "label": "Comércio atacadista e distribuição",
        # 46.2 a 46.9. O grupo 46.1 (representantes comerciais e agentes do comércio) fica de fora:
        # trabalham por comissão e não têm carteira própria — na 1ª importação real (09/11/2026)
        # eram 4 de 13 empresas do perfil.
        "cnae_prefixes": ["462", "463", "464", "465", "466", "467", "468", "469"],
        "rationale": "Vendas B2B a prazo geram carteira de duplicatas e inadimplência recorrente.",
    },
    "industria": {
        "label": "Indústria de transformação",
        "cnae_prefixes": [f"{i:02d}" for i in range(10, 34)],
        "rationale": "Faturamento a prazo para revendedores e distribuidores.",
    },
    "educacao_privada": {
        "label": "Educação privada",
        "cnae_prefixes": ["8513", "8520", "8531", "8532", "8533", "8541", "8542", "8591", "8592", "8593", "8599"],
        "rationale": "Mensalidades em atraso; cobrança de ex-alunos é demanda clássica do setor.",
    },
    "saude_privada": {
        "label": "Saúde privada (clínicas, laboratórios)",
        "cnae_prefixes": ["8610", "8630", "8640"],
        "rationale": "Particulares e convênios com glosas e atrasos.",
    },
    "telecom_provedores": {
        "label": "Telecomunicações e provedores de internet",
        "cnae_prefixes": ["6110", "6120", "6190"],
        "rationale": "Base grande de assinantes com inadimplência pulverizada.",
    },
    "imobiliario_condominios": {
        "label": "Administração imobiliária e condomínios",
        "cnae_prefixes": ["6822", "8112"],
        "rationale": "Taxas condominiais e aluguéis em atraso.",
    },
    "credito_fomento": {
        "label": "Fomento mercantil, crédito e financeiras",
        "cnae_prefixes": ["6491", "6492", "6493", "6436", "6437"],
        "rationale": "Atividade-fim é crédito: recuperação de carteira é parte do negócio.",
    },
    "utilidades": {
        "label": "Energia, água e saneamento",
        "cnae_prefixes": ["35", "36", "37"],
        "rationale": "Faturas de consumo em atraso em larga escala.",
    },
}


def profile_for(cnae: str | None, wanted: list[str] | None = None) -> str | None:
    if not cnae:
        return None
    for key, seg in SEGMENTS.items():
        if wanted and key not in wanted:
            continue
        if any(cnae.startswith(p) for p in seg["cnae_prefixes"]):
            return key
    return None
