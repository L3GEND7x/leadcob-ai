"""Classificação de contratações públicas para o LeadCob.

Três perguntas independentes, cada uma com resposta explicável:

1. ADERÊNCIA (relevance) — o objeto é serviço de cobrança/recuperação que uma
   empresa de cobrança pode prestar?
     alta      → objeto de cobrança propriamente dito
     revisar   → ambíguo (ex.: recuperação de créditos TRIBUTÁRIOS por
                 assessoria/advocacia — outro segmento de mercado)
     descartar → o termo aparece por coincidência (pedágio, arrecadação
                 bancária, cartório, gráfica...) ou não aparece no objeto
2. NATUREZA (opportunity_class) — dá para participar?
     edital_aberto        → prazo de propostas ainda não encerrou
     edital_encerrado     → prazo encerrado (sinal de mercado)
     contratacao_direta   → inexigibilidade/dispensa sem disputa (sinal)
     prazo_nao_informado  → conferir no edital
3. EVIDÊNCIA (evidence_level, definida no coletor)
     confirmada_api_oficial → registro lido na API oficial de consulta
     indicio_busca          → apenas no índice de busca do portal

"Oportunidade comprovada" = edital_aberto + aderência alta + confirmada na API
oficial. Todo o resto é sinal comercial que precisa de confirmação humana.
Nada aqui substitui a leitura do edital.

As listas abaixo foram calibradas com resultados reais do PNCP em 09/11/2026
e devem ser revistas periodicamente.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))  # horário de Brasília (sem horário de verão desde 2019)

# Termos FORTES: descrevem o próprio serviço de cobrança.
CORE_TERMS = [
    "servicos de cobranca", "servico de cobranca", "cobranca extrajudicial", "cobranca amigavel",
    "cobranca administrativa", "recuperacao de credito", "recuperacao de creditos",
    "gestao de recebiveis", "carteira de credito", "creditos inadimplidos",
    "cobranca da divida ativa", "cobranca de divida ativa", "cobranca da divida",
    "contact center de cobranca", "call center de cobranca", "assessoria de cobranca",
]
# Termos FRACOS: só mencionam o tema. Sozinhos levam a "revisar", nunca a "alta"
# (ex. real: leitura de hidrômetros com "entrega de avisos de inadimplência").
WEAK_TERMS = ["inadimplen", "negativacao", "recuperacao de ativos", "gestao de carteira", "protesto"]
# Recuperação de créditos tributários/previdenciários por assessoria ou advocacia:
# mercado diferente do de cobrança de carteiras.
TAX_TERMS = [
    "tribut", "previdenci", "fpm", "icms", "issqn", "iss ", "cfem", "pasep", "rpps", "irrf",
    "compensacao financeira", "incremento de receita", "creditos fiscais", "royalties",
    "assessoria juridica", "advocacia", "sociedade de advogados", "escritorio de advocacia",
    "auditoria tributaria", "consultoria tributaria",
]
# Termo aparece mas o objeto é outro.
EXCLUDE_TERMS = [
    "pedagio", "tags", "tag ", "decoracao", "natalin", "instituicao financeira", "instituicoes financeiras",
    "servicos bancarios", "arrecadacao bancaria", "folha de pagamento", "cartorio", "notaria",
    "servicos notariais", "grafic", "impressao", "energia eletrica", "combustive", "estacionamento rotativo",
    "zona azul", "vale-alimentacao", "vale alimentacao", "medicament", "hidrometro", "leitura informatizada",
    "entrega de faturas", "software de gestao", "licenciamento de uso",
]
COLLECTION_OF_DEBT = re.compile(r"cobranca (amigavel |administrativa |extrajudicial )?(da |de )?divida ativa")

DIRECT_MODALITIES = {"9"}       # inexigibilidade
DISPENSA_MODALITIES = {"8"}     # dispensa: às vezes com disputa eletrônica


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text.lower()).strip() + " "


def parse_dt(value) -> datetime | None:
    """Datas do PNCP vêm sem fuso (horário de Brasília) e às vezes com 9 casas decimais."""
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip().replace("Z", "+00:00")
        s = re.sub(r"(\.\d{1,6})\d*", r"\1", s)  # trunca nanossegundos
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            try:
                dt = datetime.strptime(s[:10], "%Y-%m-%d")
            except ValueError:
                return None
    return dt if dt.tzinfo else dt.replace(tzinfo=BRT)


def relevance_of(obj: str) -> tuple[str, str]:
    text = fold(obj)
    if not text.strip():
        return "descartar", "objeto não informado"
    excluded = [t.strip() for t in EXCLUDE_TERMS if t in text]
    core = [t for t in CORE_TERMS if t in text]
    weak = [t for t in WEAK_TERMS if t in text]
    tax = [t.strip() for t in TAX_TERMS if t in text]
    if excluded:
        return "descartar", f"objeto de outra natureza ({', '.join(excluded[:3])})"
    if not core and weak:
        return "revisar", f"menção indireta ({', '.join(weak[:3])}) — o objeto principal pode não ser cobrança"
    if not core:
        return "descartar", "termo de busca não aparece no objeto da contratação"
    if COLLECTION_OF_DEBT.search(text):
        return "alta", "cobrança de dívida ativa"
    if tax:
        return "revisar", (f"envolve créditos tributários/previdenciários ({', '.join(tax[:3])}) — verificar se é "
                           "cobrança de carteira ou assessoria tributária/advocacia/arrecadação")
    return "alta", f"objeto de cobrança/recuperação ({', '.join(core[:3])})"


def class_of(item: dict, now: datetime) -> tuple[str, str]:
    modality = str(item.get("modality_id") or "")
    deadline = parse_dt(item.get("deadline"))
    if modality in DIRECT_MODALITIES:
        return "contratacao_direta", "inexigibilidade: contratação direta, sem disputa"
    if deadline:
        stamp = deadline.astimezone(BRT).strftime("%d/%m/%Y %H:%M")
        if deadline > now:
            return "edital_aberto", f"propostas até {stamp} (Brasília)"
        return "edital_encerrado", f"prazo de propostas encerrado em {stamp}"
    if modality in DISPENSA_MODALITIES:
        return "contratacao_direta", "dispensa sem prazo de propostas informado"
    return "prazo_nao_informado", "prazo de propostas não informado — conferir no edital"


def classify(item: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    relevance, relevance_reason = relevance_of(f"{item.get('object', '')} {item.get('complement', '')}")
    klass, class_reason = class_of(item, now)
    evidence = item.get("evidence_level") or "indicio_busca"
    proven = relevance == "alta" and klass == "edital_aberto" and evidence == "confirmada_api_oficial"
    return {
        "relevance": relevance,
        "relevance_reason": relevance_reason,
        "opportunity_class": klass,
        "class_reason": class_reason,
        "commercial_signal": "oportunidade_comprovada" if proven else "sinal_a_confirmar",
    }


def score_procurement(item: dict) -> tuple[int, str]:
    """Prioridade de análise (0–100). Não é probabilidade de vitória."""
    score, why = 0, []
    rel = {"alta": 40, "revisar": 15}.get(item.get("relevance"), 0)
    score += rel; why.append(f"aderência {item.get('relevance')} +{rel}")
    cls = {"edital_aberto": 30, "prazo_nao_informado": 10, "edital_encerrado": 5, "contratacao_direta": 5}.get(item.get("opportunity_class"), 0)
    score += cls; why.append(f"{item.get('opportunity_class')} +{cls}")
    if item.get("evidence_level") == "confirmada_api_oficial":
        score += 15; why.append("confirmada na API oficial +15")
    if str(item.get("modality_id") or "") == "12":
        score += 5; why.append("credenciamento (admite vários prestadores) +5")
    try:
        value = float(item.get("estimated_value") or 0)  # 0 = não informado
    except (TypeError, ValueError):
        value = 0
    if value >= 1_000_000:
        score += 10; why.append("valor estimado ≥ R$ 1 mi +10")
    elif value >= 100_000:
        score += 5; why.append("valor estimado ≥ R$ 100 mil +5")
    return min(score, 100), "; ".join(why)
