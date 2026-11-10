"""Decimal agreement simulation with an auditable installment schedule."""
from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation, localcontext

CENT = Decimal('0.01')


def money(value):
    result = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    if not result.is_finite():
        raise ValueError('Valor monetário inválido.')
    return result


def month_after(start, count):
    month = start.month - 1 + count
    year, month = start.year + month // 12, month % 12 + 1
    return date(year, month, min(start.day, monthrange(year, month)[1]))


def simulate(p):
    try:
        return _simulate(p)
    except (InvalidOperation, OverflowError) as exc:
        raise ValueError('Premissas excedem os limites de cálculo.') from exc


def _simulate(p):
    valor = money(p['valor_original'])
    if valor <= 0:
        raise ValueError('Valor original deve ser positivo.')
    venc, base = date.fromisoformat(p['vencimento']), date.fromisoformat(p['data_base'])
    dias = max(0, (base - venc).days)
    meses = Decimal(dias) / 30
    rates = {key: Decimal(str(p.get(key) or 0)) / 100 for key in
             ('multa_pct', 'juros_mes_pct', 'correcao_pct', 'desconto_pct', 'juros_parcelamento_mes_pct')}
    if any(not rate.is_finite() for rate in rates.values()):
        raise ValueError('Percentuais inválidos.')
    multa_p, juros_p, corr_p, desc_p, jparc = rates.values()
    if min(multa_p, juros_p, desc_p, jparc) < 0 or desc_p > 1 or corr_p < -1:
        raise ValueError('Percentuais inválidos.')
    correcao = money(valor * corr_p) if dias else money(0)
    corrigido = valor + correcao
    multa = money(corrigido * multa_p) if dias else money(0)
    composto = p.get('juros_tipo') == 'composto'
    with localcontext() as ctx:
        ctx.prec = 40
        juros = money(corrigido * ((1 + juros_p) ** meses - 1) if composto else corrigido * juros_p * meses)
    total = corrigido + multa + juros
    encargos = correcao + multa + juros
    sobre = p.get('desconto_sobre') or 'encargos'
    desconto = money(max(Decimal(0), encargos if sobre == 'encargos' else total) * desc_p)
    acordado = total - desconto
    entrada = money(p.get('entrada') or 0)
    if entrada < 0 or entrada > acordado:
        raise ValueError('Entrada deve estar entre zero e o valor acordado.')
    n = int(p.get('parcelas') or 1)
    if not 1 <= n <= 120:
        raise ValueError('Parcelas: de 1 a 120.')
    saldo = acordado - entrada
    parcela = money(saldo * jparc / (1 - (1 + jparc) ** -n) if jparc > 0 else saldo / n)
    first = date.fromisoformat(p['primeiro_vencimento']) if p.get('primeiro_vencimento') else month_after(base, 1)
    if first < base:
        raise ValueError('Primeira parcela deve vencer na data-base ou depois dela.')
    schedule = []
    for i in range(n):
        interest = money(saldo * jparc)
        payment = saldo + interest if i == n - 1 else min(parcela, saldo + interest)
        saldo = money(saldo + interest - payment)
        schedule.append({'numero': i + 1, 'vencimento': month_after(first, i).isoformat(),
                         'valor': float(payment), 'juros': float(interest), 'saldo': float(saldo)})
    received = entrada + sum((money(row['valor']) for row in schedule), Decimal(0))
    notices = ['Taxas informadas pelo usuário. Confira os limites contratuais e legais aplicáveis.',
               'Meses de atraso = dias / 30. Parcelas mensais com arredondamento a centavos e ajuste final.']
    if not (multa_p or juros_p or corr_p):
        notices.insert(0, 'Nenhum encargo informado: o total considera só o valor original.')
    result = {key: float(value) for key, value in {
        'valor_original': valor, 'correcao': correcao, 'valor_corrigido': corrigido, 'multa': multa, 'juros': juros,
        'total_atualizado': total, 'desconto': desconto, 'valor_acordado': acordado, 'entrada': entrada,
        'valor_parcela': parcela, 'total_a_receber': received}.items()}
    return {**result, 'dias_atraso': dias, 'meses_considerados': float(round(meses, 4)), 'parcelas': n,
            'cronograma': schedule, 'avisos': notices, 'memoria': [
                f'Atraso de {dias} dias. Juros {"compostos" if composto else "simples"} sobre o valor corrigido.',
                f'Correção {corr_p * 100}%, multa {multa_p * 100}%, juros mensais {juros_p * 100}%.',
                f'Desconto {desc_p * 100}% sobre {sobre}. Juros do parcelamento {jparc * 100}% ao mês.',
                f'Entrada {entrada:.2f} e soma das parcelas {received - entrada:.2f}. Total {received:.2f}.']}
