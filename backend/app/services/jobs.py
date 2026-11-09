"""Classificação de vagas para o LeadCob — pelo TÍTULO da vaga.

Calibrado com 928 vagas reais de 14 boards (Greenhouse/Lever) em 09/11/2026:
- casar termos na DESCRIÇÃO gerou 36 de 45 acertos e quase todos eram ruído
  (ex.: dezenas de "Gerente de Relacionamento" que citam "cobrança" de passagem);
- "analista de crédito"/"credit analyst" é concessão de crédito, não cobrança.

Saídas:
  relevance       alta | descartar
  role_type       operacao_interna  → empresa opera cobrança com equipe própria
                                      (argumento: terceirizar/complementar)
                  estrategia_dados  → área de recuperação estruturada; em geral já
                                      trabalha com assessorias (argumento: credenciamento)
"""
from __future__ import annotations

import html
import re
import unicodedata

# "recovery" e "collection" sozinhos ficaram de fora: casam com "Disaster Recovery" e "data collection".
STRONG = ["cobranca", "collections", "recuperacao de credito", "recuperacao de ativos",
          "contas a receber", "accounts receivable", "negociacao de divida", "negociacao de debito",
          "inadimplencia", "credit recovery", "debt recovery"]
CREDIT_ONLY = ["analista de credito", "credit analyst", "credito imobiliario", "analise de credito", "credit analysis",
               "concessao de credito"]
STRATEGY = ["politica", "estrateg", "data", "science", "cientista", "analytics", "especialista", "specialist",
            "business analyst", "produto", "product", "sistemas", "manager", "gerente", "head", "lider", "lead",
            "coordinator", "coordenador", "director", "diretor"]
BRAZIL = re.compile(r"bras|brazil|\b(sp|rj|mg|pr|sc|rs|df|go|ba|pe|ce|am|pa|es)\b|sao paulo|rio de janeiro|belo horizonte|"
                    r"curitiba|florianopolis|porto alegre|recife|salvador|fortaleza|manaus|brasilia|campinas|remot", re.I)
COMPETITOR_CNAE = "8291"  # 8291-1/00 Atividades de cobranças e informações cadastrais


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text.lower()).strip()


def strip_html(raw: str) -> str:
    """Greenhouse devolve o HTML escapado (&lt;p&gt;...): desescapar ANTES de remover tags."""
    text = html.unescape(html.unescape(raw or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def classify_job(title: str, description: str = "", location: str = "") -> dict:
    t = fold(title)
    strong = [k for k in STRONG if re.search(rf"\b{re.escape(k)}\b", t)]
    if not strong:
        if any(k in t for k in CREDIT_ONLY):
            return {"relevance": "descartar", "relevance_reason": "concessão/análise de crédito, não cobrança"}
        if any(k in fold(description) for k in ("cobranca", "collections", "recuperacao de credito")):
            return {"relevance": "descartar", "relevance_reason": "termo só na descrição da vaga"}
        return {"relevance": "descartar", "relevance_reason": "vaga sem relação com cobrança"}
    role = "estrategia_dados" if any(k in t for k in STRATEGY) else "operacao_interna"
    loc = fold(location)
    in_brazil = bool(BRAZIL.search(loc)) if loc else None
    reason = f"título indica cobrança/recuperação ({', '.join(strong[:3])})"
    if in_brazil is False:
        reason += f" — localização fora do Brasil ({location})"
    return {"relevance": "alta" if in_brazil is not False else "revisar", "relevance_reason": reason,
            "role_type": role, "in_brazil": in_brazil}


def score_job(item: dict) -> tuple[int, str]:
    if item.get("competitor"):
        return 0, "empresa do ramo de cobrança (CNAE 8291-1/00): concorrente, não cliente"
    score, why = 0, []
    rel = {"alta": 40, "revisar": 15}.get(item.get("relevance"), 0)
    score += rel; why.append(f"aderência {item.get('relevance')} +{rel}")
    role = {"operacao_interna": 25, "estrategia_dados": 20}.get(item.get("role_type"), 0)
    score += role; why.append(f"{item.get('role_type')} +{role}")
    if item.get("open", True):
        score += 15; why.append("vaga publicada na consulta +15")
    if item.get("cnpj"):
        score += 10; why.append("empresa identificada por CNPJ +10")
    return min(score, 100), "; ".join(why)
