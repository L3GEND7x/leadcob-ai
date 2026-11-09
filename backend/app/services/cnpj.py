"""CNPJ: validação (numérico e alfanumérico) e normalização com lista branca de campos.

CNPJ alfanumérico (IN RFB nº 2.229/2024, novas inscrições a partir de jul/2026):
12 posições alfanuméricas + 2 dígitos verificadores numéricos. O valor de cada
caractere no cálculo do DV é (código ASCII − 48), o que mantém o cálculo
idêntico para CNPJs numéricos.

PRIVACIDADE: os registros públicos do CNPJ trazem dados de pessoas físicas
(quadro societário com nomes e CPF parcial; e-mail e telefone que, na prática,
muitas vezes são do contador ou de um funcionário — verificado em amostra real
de 09/11/2026). O LeadCob guarda apenas dados da pessoa jurídica listados em
`KEEP`; sócios, e-mail, telefone e endereço completo são descartados.
"""
from __future__ import annotations

import re

WEIGHTS_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
WEIGHTS_2 = [6] + WEIGHTS_1

PORTE = {"00": "NÃO INFORMADO", "01": "MICRO EMPRESA", "03": "EMPRESA DE PEQUENO PORTE", "05": "DEMAIS",
         "0": "NÃO INFORMADO", "1": "MICRO EMPRESA", "3": "EMPRESA DE PEQUENO PORTE", "5": "DEMAIS"}
SITUACAO = {"01": "NULA", "02": "ATIVA", "03": "SUSPENSA", "04": "INAPTA", "08": "BAIXADA",
            "1": "NULA", "2": "ATIVA", "3": "SUSPENSA", "4": "INAPTA", "8": "BAIXADA"}

KEEP = ["cnpj", "razao_social", "nome_fantasia", "cnae_principal", "cnae_descricao", "cnaes_secundarios",
        "situacao_cadastral", "porte", "natureza_juridica", "municipio", "uf", "capital_social",
        "data_inicio_atividade", "matriz", "opcao_mei"]


def clean_cnpj(value) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", str(value or "")).upper()


def _dv(base: str, weights: list[int]) -> str:
    total = sum((ord(c) - 48) * w for c, w in zip(base, weights))
    rest = total % 11
    return "0" if rest < 2 else str(11 - rest)


def is_valid_cnpj(value) -> bool:
    c = clean_cnpj(value)
    if not re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", c) or len(set(c)) == 1:
        return False
    d1 = _dv(c[:12], WEIGHTS_1)
    return c[12] == d1 and c[13] == _dv(c[:12] + d1, WEIGHTS_2)


def format_cnpj(value) -> str:
    c = clean_cnpj(value)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else c


def normalize_api(payload: dict, source: str) -> dict:
    """Resposta da BrasilAPI ou da Minha Receita (mesmo esquema) → campos permitidos."""
    def txt(k):
        v = payload.get(k)
        return str(v).strip() if v not in (None, "") else None
    cnae = payload.get("cnae_fiscal")
    out = {
        "cnpj": clean_cnpj(payload.get("cnpj")),
        "razao_social": txt("razao_social"),
        "nome_fantasia": txt("nome_fantasia"),
        "cnae_principal": f"{int(cnae):07d}" if cnae not in (None, "") else None,
        "cnae_descricao": txt("cnae_fiscal_descricao"),
        "cnaes_secundarios": [f"{int(x['codigo']):07d}" for x in payload.get("cnaes_secundarios") or []
                              if isinstance(x, dict) and x.get("codigo")],
        "situacao_cadastral": txt("descricao_situacao_cadastral"),
        "porte": txt("porte"),
        "natureza_juridica": txt("natureza_juridica"),
        "municipio": txt("municipio"),
        "uf": txt("uf"),
        "capital_social": float(payload["capital_social"]) if payload.get("capital_social") not in (None, "") else None,
        "data_inicio_atividade": txt("data_inicio_atividade"),
        "matriz": payload.get("identificador_matriz_filial") == 1,
        "opcao_mei": payload.get("opcao_pelo_mei"),
        "source": source,
    }
    return {k: out[k] for k in KEEP + ["source"]}
