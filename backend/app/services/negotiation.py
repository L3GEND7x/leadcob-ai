"""Laboratório de negociação (Etapa 2): calculadora com premissas informadas pelo usuário.

O sistema NÃO presume taxa de juros, multa ou índice de correção: tudo vem do usuário. Se uma premissa
não é informada, ela vale zero e o resultado diz isso. Limites legais e contratuais de encargos devem
ser conferidos à parte. Convenção de prazo: meses = dias / 30.
"""
from __future__ import annotations

from datetime import date


def simulate(p: dict) -> dict:
    valor = float(p["valor_original"])
    if valor <= 0:
        raise ValueError("Valor original deve ser positivo.")
    venc, base = date.fromisoformat(p["vencimento"]), date.fromisoformat(p["data_base"])
    dias = max(0, (base - venc).days)
    meses = dias / 30
    pct = lambda k: float(p.get(k) or 0) / 100
    multa_p, juros_p, corr_p, desc_p, jparc = pct("multa_pct"), pct("juros_mes_pct"), pct("correcao_pct"), pct("desconto_pct"), pct("juros_parcelamento_mes_pct")
    if min(multa_p, juros_p, desc_p, jparc) < 0 or desc_p > 1:
        raise ValueError("Percentuais inválidos.")
    composto = p.get("juros_tipo") == "composto"
    correcao = valor * corr_p if dias else 0.0
    corrigido = valor + correcao
    multa = corrigido * multa_p if dias else 0.0
    juros = corrigido * ((1 + juros_p) ** meses - 1) if composto else corrigido * juros_p * meses
    total = corrigido + multa + juros
    encargos = correcao + multa + juros
    sobre = p.get("desconto_sobre") or "encargos"
    desconto = (encargos if sobre == "encargos" else total) * desc_p
    acordado = total - desconto
    entrada = float(p.get("entrada") or 0)
    if entrada < 0 or entrada > acordado:
        raise ValueError("Entrada deve estar entre zero e o valor acordado.")
    n = int(p.get("parcelas") or 1)
    if not 1 <= n <= 120:
        raise ValueError("Parcelas: de 1 a 120.")
    saldo = acordado - entrada
    parcela = saldo * jparc / (1 - (1 + jparc) ** -n) if jparc > 0 else saldo / n
    r = lambda x: round(x + 0.0, 2)
    avisos = ["Todas as taxas e índices foram informados por você; o sistema não presume nenhum.",
              "Confira no contrato e na legislação aplicável os limites de multa, juros e correção. [NECESSÁRIO CONFERIR]"]
    if not (multa_p or juros_p or corr_p):
        avisos.insert(0, "Nenhum encargo informado: o total considera só o valor original.")
    return {
        "dias_atraso": dias, "meses_considerados": round(meses, 4),
        "valor_original": r(valor), "correcao": r(correcao), "valor_corrigido": r(corrigido), "multa": r(multa), "juros": r(juros),
        "total_atualizado": r(total), "desconto": r(desconto), "valor_acordado": r(acordado), "entrada": r(entrada),
        "parcelas": n, "valor_parcela": r(parcela), "total_a_receber": r(entrada + parcela * n),
        "memoria": [
            f"Atraso: {dias} dia(s) entre {venc:%d/%m/%Y} e {base:%d/%m/%Y} ({meses:.2f} meses de 30 dias).",
            f"Correção informada: {corr_p*100:.2f}% sobre o original = {correcao:.2f}.",
            f"Multa informada: {multa_p*100:.2f}% sobre o valor corrigido = {multa:.2f}.",
            f"Juros informados: {juros_p*100:.2f}% ao mês, {'compostos' if composto else 'simples'} = {juros:.2f}.",
            f"Desconto: {desc_p*100:.2f}% sobre {'os encargos' if sobre == 'encargos' else 'o total'} = {desconto:.2f}.",
            f"Parcelamento: entrada {entrada:.2f} + {n} parcela(s) de {parcela:.2f}"
            + (f" (juros de {jparc*100:.2f}% a.m., tabela Price)." if jparc else " (sem juros)."),
        ],
        "avisos": avisos,
    }
