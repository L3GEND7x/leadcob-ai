"""Inteligência de cobrança (Etapa 2): carteira de títulos de um CLIENTE CONTRATANTE.

Separada da prospecção. Importa só o necessário para a análise de atraso (valor, vencimento,
pagamento, referência do título e, opcionalmente, se o devedor é PJ ou PF). Colunas com dados
do devedor (nome, CPF, CNPJ, e-mail, telefone, endereço) são IGNORADAS na importação.
As estratégias por faixa são sugestões de rotina operacional; medidas como notificação, protesto,
negativação ou ação judicial exigem decisão humana e análise jurídica.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

BANDS = [
    ("a_vencer", "A vencer", None, 0),
    ("d1_7", "1 a 7 dias", 1, 7),
    ("d8_30", "8 a 30 dias", 8, 30),
    ("d31_60", "31 a 60 dias", 31, 60),
    ("d61_90", "61 a 90 dias", 61, 90),
    ("d91_180", "91 a 180 dias", 91, 180),
    ("d180", "Mais de 180 dias", 181, None),
]
STRATEGY = {
    "a_vencer": "Prevenção: lembrete antes do vencimento com 2ª via e canal de pagamento.",
    "d1_7": "Lembrete cordial com 2ª via; confirmar se a cobrança foi recebida.",
    "d8_30": "Contato ativo (telefone, e-mail ou WhatsApp institucional) para entender o motivo e propor a regularização.",
    "d31_60": "Negociação estruturada: proposta de acordo com premissas definidas pelo credor (use o Laboratório de negociação).",
    "d61_90": "Comunicação formal por escrito (notificação extrajudicial), revisada por profissional habilitado.",
    "d91_180": "Avaliar medidas como protesto ou registro em cadastro de inadimplentes, conforme a lei e o contrato. "
               "Exige análise jurídica e documental. [NECESSÁRIO CONFERIR requisitos legais na fonte oficial]",
    "d180": "Avaliar viabilidade de cobrança judicial ou provisão/baixa contábil, com análise de custo, documentos e prazos. "
            "[NECESSÁRIO CONFERIR prazos prescricionais aplicáveis]",
}
ALIASES = {
    "amount": ["valor", "valor_aberto", "saldo", "valor_titulo", "amount", "valor_original"],
    "due_date": ["vencimento", "data_vencimento", "dt_vencimento", "venc", "due_date"],
    "paid_date": ["pagamento", "data_pagamento", "pago_em", "dt_pagamento", "paid_date", "data_baixa"],
    "ref": ["titulo", "documento", "nota", "nf", "numero", "referencia", "ref", "id"],
    "debtor_type": ["tipo_devedor", "tipo_cliente", "pessoa", "tipo_pessoa"],
}
PERSONAL = re.compile(r"cpf|cnpj|nome|razao|devedor|cliente|email|e_mail|telefone|celular|fone|endereco|logradouro|cep")
MAX_ROWS = 50000


def _norm(h: str) -> str:
    h = unicodedata.normalize("NFKD", h).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"[^a-z0-9]+", "_", h).strip("_")


def parse_money(v: str, number_format: str = "auto") -> float:
    s = (v or "").strip().replace("R$", "").replace(" ", "")
    if not re.fullmatch(r"-?[0-9]+(?:[.,][0-9]+)*", s):
        raise ValueError("valor inválido")
    if number_format == "br":
        s = s.replace(".", "").replace(",", ".")
    elif number_format == "us":
        s = s.replace(",", "")
    elif "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif re.fullmatch(r"-?\d+[.,]\d{3}", s):
        raise ValueError("valor ambíguo: escolha formato brasileiro ou internacional")
    else:
        s = s.replace(",", ".")
    try:
        value = Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError("valor inválido") from exc
    if not value.is_finite() or abs(value) > Decimal("999999999999.99"):
        raise ValueError("valor fora do limite")
    return float(value)


def parse_date(v: str) -> date:
    v = (v or "").strip()[:10]
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"data inválida: {v!r}")


def parse_csv(text: str, number_format: str = "auto") -> dict:
    text = text.lstrip("﻿")
    sample = text[:4000]
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
    except csv.Error:
        delim = ";"
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    header = next(reader, None)
    if not header:
        raise ValueError("Arquivo vazio.")
    cols = [_norm(h) for h in header]
    pick, used = {}, set()
    for field, names in ALIASES.items():
        for i, c in enumerate(cols):
            if c in names and i not in used:
                pick[field] = i; used.add(i); break
    if "amount" not in pick or "due_date" not in pick:
        raise ValueError("O arquivo precisa das colunas de valor e de vencimento (ex.: 'valor' e 'vencimento').")
    ignored = [header[i] for i, c in enumerate(cols) if i not in used]
    personal = [header[i] for i, c in enumerate(cols) if i not in used and PERSONAL.search(c)]
    items, errors, duplicates = [], [], []
    error_count = 0
    seen = set()
    for n, row in enumerate(reader, start=2):
        if not any(x.strip() for x in row):
            continue
        if len(items) >= MAX_ROWS:
            errors.append({"linha": n, "erro": f"limite de {MAX_ROWS} títulos por importação"}); break
        try:
            get = lambda f: row[pick[f]].strip() if f in pick and pick[f] < len(row) else ""
            amount = parse_money(get("amount"), number_format)
            if amount <= 0:
                raise ValueError("valor deve ser positivo")
            due = parse_date(get("due_date"))
            paid = parse_date(get("paid_date")) if get("paid_date") else None
            ref = get("ref")[:80] or None
            if ref and re.fullmatch(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}", ref):
                ref = None   # parece CPF: não guardar
            dt = get("debtor_type").upper()
            dt = "PF" if dt in ("PF", "FISICA", "PESSOA FISICA", "F") else "PJ" if dt in ("PJ", "JURIDICA", "PESSOA JURIDICA", "J") else None
            identity = (ref, amount, due.isoformat(), paid.isoformat() if paid else None)
            if ref and identity in seen:
                duplicates.append(n)
            seen.add(identity)
            items.append({"ref": ref, "amount": amount, "due_date": due.isoformat(), "paid_date": paid.isoformat() if paid else None,
                          "debtor_type": dt})
        except (ValueError, IndexError) as exc:
            error_count += 1
            if len(errors) < 50:
                errors.append({"linha": n, "erro": str(exc)})
    return {"items": items, "errors": errors, "ignored_columns": ignored, "personal_columns_dropped": personal, "error_count": error_count, "possible_duplicates": duplicates}


def band_of(days: int) -> str:
    for key, _, lo, hi in BANDS:
        if (lo is None or days >= lo) and (hi is None or days <= hi):
            return key
    return "d180"


def analyze(items: list[dict], reference: date) -> dict:
    agg = {k: {"key": k, "label": l, "titulos": 0, "valor": Decimal(0)} for k, l, _, _ in BANDS}
    paid_n, paid_v, pf = 0, Decimal(0), 0
    for it in items:
        original = Decimal(str(it["amount"]))
        events = it.get("events", [])
        if events:
            paid_v += sum((Decimal(str(e["amount"])) for e in events
                           if e["kind"] == "payment" and date.fromisoformat(e["effective_date"]) <= reference), Decimal(0))
            paid_v -= sum((Decimal(str(e["amount"])) for e in events
                           if e["kind"] == "reversal" and e.get("reversed_kind") == "payment"
                           and date.fromisoformat(e["effective_date"]) <= reference), Decimal(0))
            applied = sum((Decimal(str(e["amount"])) * (-1 if e["kind"] == "reversal" else 1)
                           for e in events if date.fromisoformat(e["effective_date"]) <= reference), Decimal(0))
            amount = max(Decimal(0), original - applied)
            if amount == 0:
                paid_n += 1
                continue
        else:
            amount = original
            if it.get("paid_date") and date.fromisoformat(it["paid_date"]) <= reference:
                paid_n += 1
                paid_v += amount
                continue
        days = (reference - date.fromisoformat(it["due_date"])).days
        b = agg[band_of(days)]
        b["titulos"] += 1; b["valor"] += amount
        pf += it.get("debtor_type") == "PF"
    open_v = sum(b["valor"] for b in agg.values())
    overdue_v = open_v - agg["a_vencer"]["valor"]
    overdue_n = sum(b["titulos"] for k, b in agg.items() if k != "a_vencer")
    bands = []
    for k, _, _, _ in BANDS:
        b = agg[k]
        b["valor"] = float(round(b["valor"], 2))
        b["pct_valor"] = round(100 * Decimal(str(b["valor"])) / open_v, 1) if open_v else 0.0
        b["estrategia"] = STRATEGY[k]
        bands.append(b)
    top = max((b for b in bands if b["key"] != "a_vencer"), key=lambda b: b["valor"], default=None)
    return {
        "data_referencia": reference.isoformat(),
        "resumo": {"titulos_abertos": sum(b["titulos"] for b in bands), "valor_aberto": round(open_v, 2),
                   "titulos_vencidos": overdue_n, "valor_vencido": round(overdue_v, 2),
                   "pct_vencido": round(100 * overdue_v / open_v, 1) if open_v else 0.0,
                   "ticket_medio_vencido": round(overdue_v / overdue_n, 2) if overdue_n else 0.0,
                   "titulos_pagos": paid_n, "valor_pago": round(paid_v, 2), "titulos_pf_abertos": pf,
                   "maior_concentracao": top["label"] if top and top["valor"] > 0 else None},
        "faixas": bands,
        "avisos": ["Estratégias são sugestões de rotina; a decisão e a execução são humanas.",
                   "Cobrança de pessoa física segue regras de defesa do consumidor; confirme o enquadramento antes de agir."
                   + (" Há títulos PF nesta carteira." if pf else "")],
    }
