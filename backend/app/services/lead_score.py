"""Lead score explicável (0–100) por empresa.

Não é probabilidade de contratação nem de inadimplência: é uma ordem de prioridade
de trabalho comercial, com cada ponto justificado. Cada componente declara a natureza
da informação que o sustenta:
  fato     — consta de fonte verificável (cadastro, edital, vaga, histórico do CRM);
  indício  — sugere algo, mas não comprova (porte e capital como sinal de volume);
  hipótese — premissa comercial (setor costuma ter carteira a receber).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.services.crm import CLOSED, as_utc, stage_of
from app.services.segments import SEGMENTS, profile_for

BANDS = [(80, "alta", "Prioridade alta"), (60, "intermediaria", "Prioridade intermediária"),
         (40, "pesquisar", "Pesquisar melhor"), (0, "baixa", "Baixa prioridade")]

HIGH_FIT = {"atacado", "varejo", "industria", "credito_fomento", "financeiro", "educacao_privada", "saude_privada",
            "imobiliario_condominios", "condominios", "telecom_provedores", "utilidades", "transporte_logistica",
            "construcao", "concessionarias_veiculos", "planos_seguros", "academias_clubes", "servicos_empresariais",
            "tecnologia_midia", "agro"}
MID_FIT = {"servicos_profissionais", "hospedagem_alimentacao", "cultura_lazer", "servicos_pessoais", "associacoes",
           "demais_setores", "setor_publico"}


def band(score: int) -> tuple[str, str]:
    for floor, key, label in BANDS:
        if score >= floor:
            return key, label
    return "baixa", "Baixa prioridade"


def signal_strength(o) -> tuple[int, str]:
    """Força de um sinal (oportunidade captada) — 0 a 30."""
    cls, sig = o.opportunity_class, o.commercial_signal
    if o.kind == "public_procurement":
        if sig == "oportunidade_comprovada":
            return 30, "edital aberto, aderente e confirmado na API oficial"
        if cls == "edital_aberto":
            return 15, "edital aberto com aderência a revisar"
        return 8, "contratação pública já encerrada ou direta (o órgão compra este tipo de serviço)"
    if o.kind == "hiring":
        if cls == "concorrente":
            return 0, "vaga em empresa de cobrança (concorrente)"
        if cls == "vaga_encerrada":
            return 8, "vaga de cobrança encerrada"
        if cls == "operacao_interna":
            return 25, "vaga para equipe própria de cobrança"
        if cls == "estrategia_dados":
            return 20, "vaga em área de recuperação de crédito estruturada"
        return 15, "vaga ligada a cobrança"
    if (o.evidence or "").strip():
        return 15, "sinal cadastrado manualmente com evidência"
    return 5, "sinal cadastrado sem evidência"


def _days(dt) -> int | None:
    dt = as_utc(dt)
    return None if dt is None else max(0, (datetime.now(timezone.utc) - dt).days)


def score_company(c, settings: dict, suppressed: bool = False) -> dict:
    parts: list[dict] = []

    def add(key, label, points, reason, nature):
        parts.append({"key": key, "label": label, "points": points, "reason": reason, "nature": nature})

    signals = [o for o in c.opportunities if o.status != "discarded"]
    competitor = (c.cnae_main or "").startswith("8291") or any(o.opportunity_class == "concorrente" for o in signals)
    stage = stage_of(c)

    # 1. Aderência ao serviço (hipótese comercial pelo setor)
    prof = c.target_profile or (profile_for(c.cnae_main) if c.cnae_main else None)
    if competitor:
        add("aderencia", "Aderência ao serviço", 0, "empresa do ramo de cobrança: concorrente, não cliente", "fato")
    elif prof in HIGH_FIT:
        add("aderencia", "Aderência ao serviço", 22, f"setor costuma ter carteira a receber ({SEGMENTS[prof]['label']})", "hipótese")
    elif prof == "representacao_comercial":
        add("aderencia", "Aderência ao serviço", 6, "representação comercial: carteira própria pequena", "hipótese")
    elif prof in MID_FIT:
        add("aderencia", "Aderência ao serviço", 12, f"setor com recebíveis menos típicos ({SEGMENTS.get(prof, {}).get('label', prof)})", "hipótese")
    elif c.segment == "Órgão público":
        add("aderencia", "Aderência ao serviço", 12, "órgão público: só contrata por licitação ou credenciamento, nos termos do edital", "hipótese")
    else:
        seg = f" (segmento informado: {c.segment})" if c.segment else ""
        add("aderencia", "Aderência ao serviço", 10, f"setor sem CNAE cadastrado{seg}", "hipótese")

    # 2. Evidência comercial (fatos captados)
    if signals:
        strengths = sorted((signal_strength(o) for o in signals), reverse=True)
        pts = min(30, strengths[0][0] + 3 * (len(strengths) - 1))
        extra = f" + {len(strengths) - 1} outro(s) sinal(is)" if len(strengths) > 1 else ""
        add("evidencia", "Evidência comercial", pts, strengths[0][1] + extra, "fato")
    else:
        add("evidencia", "Evidência comercial", 0, "nenhum sinal captado: só cadastro", "fato")

    # 3. Atualidade do sinal mais recente
    ages = [d for d in (_days(o.collected_at) for o in signals) if d is not None]
    if ages:
        d = min(ages)
        pts = 10 if d <= 30 else 6 if d <= 90 else 3 if d <= 180 else 0
        add("atualidade", "Atualidade", pts, f"sinal mais recente captado há {d} dia(s)", "fato")
    else:
        add("atualidade", "Atualidade", 0, "sem sinal datado", "fato")

    # 4. Potencial de volume (indício; só com dado cadastral)
    pts, why = 0, []
    if c.company_size == "DEMAIS":
        pts += 6; why.append("porte 'demais' (acima de EPP)")
    elif c.company_size == "EMPRESA DE PEQUENO PORTE":
        pts += 4; why.append("empresa de pequeno porte")
    elif c.company_size == "MICRO EMPRESA":
        pts += 2; why.append("microempresa")
    if c.capital_social and c.capital_social >= 1_000_000:
        pts += 4; why.append("capital social ≥ R$ 1 mi")
    elif c.capital_social and c.capital_social >= 100_000:
        pts += 2; why.append("capital social ≥ R$ 100 mil")
    add("potencial", "Potencial de volume", min(pts, 10), ", ".join(why) or "sem dado de porte ou capital", "indício")

    # 5. Compatibilidade geográfica (fato x configuração)
    ufs = [u.upper() for u in settings.get("ufs_atuacao") or []]
    if not ufs:
        add("geografia", "Compatibilidade geográfica", 5, "nenhuma UF de atuação configurada (Brasil inteiro)", "fato")
    elif c.state and c.state.upper() in ufs:
        add("geografia", "Compatibilidade geográfica", 10, f"{c.state} está nas UFs de atuação", "fato")
    elif not c.state:
        add("geografia", "Compatibilidade geográfica", 3, "UF não informada", "fato")
    else:
        add("geografia", "Compatibilidade geográfica", 0, f"{c.state} fora das UFs de atuação", "fato")

    # 6. Canal institucional de contato
    if c.website or c.institutional_email:
        add("canal", "Canal institucional", 5, "site ou e-mail institucional cadastrado", "fato")
    else:
        add("canal", "Canal institucional", 0, "sem canal institucional cadastrado", "fato")

    # 7. Possibilidade de contratação
    pts, why = 0, []
    if (c.registration_status or "").upper() == "ATIVA":
        pts += 5; why.append("cadastro ativo na Receita")
    elif not c.registration_status and c.segment == "Órgão público":
        pts += 5; why.append("órgão público com contratação publicada")
    if any(o.opportunity_class in ("edital_aberto", "operacao_interna", "estrategia_dados") for o in signals):
        pts += 5; why.append("demanda aberta agora (edital ou vaga)")
    add("contratacao", "Possibilidade de contratação", pts, ", ".join(why) or "sem indicação de demanda aberta", "fato")

    # 8. Histórico de interações do CRM
    kinds = {i.kind for i in c.interactions}
    if stage == "perdido":
        add("historico", "Histórico comercial", -20, "oportunidade marcada como perdida", "fato")
    elif stage == "acompanhar_futuramente":
        add("historico", "Histórico comercial", -5, "marcada para acompanhar no futuro", "fato")
    elif kinds & {"resposta", "reuniao", "proposta"}:
        add("historico", "Histórico comercial", 10, "já houve resposta, reunião ou proposta", "fato")
    else:
        add("historico", "Histórico comercial", 0, "sem interação registrada", "fato")

    total = max(0, min(100, sum(p["points"] for p in parts)))
    inactive = (c.registration_status or "").upper() in ("BAIXADA", "INAPTA", "NULA", "SUSPENSA")
    if competitor or suppressed or stage == "nao_contatar" or inactive:
        total = 0
    key, label = band(total)
    if competitor:
        key, label = "concorrente", "Concorrente"
    elif suppressed or stage == "nao_contatar":
        key, label = "nao_contatar", "Não contatar"
    elif inactive:
        key, label = "inativa", f"Cadastro {c.registration_status.lower()}"
    return {"score": total, "band": key, "band_label": label, "components": parts, "closed": stage in CLOSED,
            "disclaimer": "Ordem de prioridade comercial, não probabilidade de contratação ou de inadimplência."}
