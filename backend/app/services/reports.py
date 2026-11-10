"""Relatórios do período (Etapa 3): só contagens sobre o que está no banco, sem projeções."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.db.models import AuditLog, Company, Interaction, Opportunity, Task
from app.services.crm import MANAUS, STAGE_LABEL, as_utc, now

ACTIVITY = [("contato", "Contatos"), ("follow_up", "Follow-ups"), ("resposta", "Respostas"), ("reuniao", "Reuniões"),
            ("proposta", "Propostas"), ("contrato", "Contratos")]
FUNNEL = ["contato", "resposta", "reuniao", "proposta", "contrato"]


def period(inicio: date | None, fim: date | None, dias: int | None) -> tuple[date, date]:
    today = now().astimezone(MANAUS).date()
    fim = fim or today
    inicio = inicio or fim - timedelta(days=(dias or 7) - 1)
    if inicio > fim:
        raise ValueError("A data inicial é posterior à final.")
    if (fim - inicio).days > 366:
        raise ValueError("Período máximo: 1 ano.")
    return inicio, fim


def _bounds(inicio: date, fim: date):
    a = datetime.combine(inicio, time.min, MANAUS)
    b = datetime.combine(fim + timedelta(days=1), time.min, MANAUS)
    return a, b


def _in(dt, a, b) -> bool:
    dt = as_utc(dt)
    return dt is not None and a <= dt < b


def summary(db: Session, inicio: date, fim: date) -> dict:
    a, b = _bounds(inicio, fim)
    inter = [i for i in db.query(Interaction).all() if _in(i.happened_at, a, b)]
    by_kind = Counter(i.kind for i in inter)
    companies_by_kind = {k: {i.company_id for i in inter if i.kind == k} for k, _ in ACTIVITY}
    contacted = {i.company_id for i in inter if i.kind in ("contato", "follow_up", "proposta")}
    # conversão: das empresas contatadas no período, quantas avançaram (qualquer registro até o fim do período)
    later = {}
    if contacted:
        for i in db.query(Interaction).filter(Interaction.company_id.in_(contacted)).all():
            if as_utc(i.happened_at) and as_utc(i.happened_at) < b:
                later.setdefault(i.kind, set()).add(i.company_id)
    conversion = []
    for k in FUNNEL:
        n = len(contacted) if k == "contato" else len(later.get(k, set()) & contacted)
        conversion.append({"etapa": dict(ACTIVITY)[k], "empresas": n,
                           "pct_contatadas": round(100 * n / len(contacted), 1) if contacted else None})
    stage_moves = [x for x in db.query(AuditLog).filter(AuditLog.event == "stage_changed").all() if _in(x.created_at, a, b)]
    entered = Counter((x.details or {}).get("to") for x in stage_moves)
    lost_ids = {x.entity_id for x in stage_moves if (x.details or {}).get("to") == "perdido"}
    reasons = Counter()
    for c in db.query(Company).filter(Company.id.in_(lost_ids or [-1])):
        reasons[(c.lost_reason or "sem motivo informado").strip()[:120]] += 1
    signals = [o for o in db.query(Opportunity).filter(Opportunity.status != "discarded").all() if _in(o.collected_at, a, b)]
    tasks = db.query(Task).all()
    real_now = now()
    return {
        "periodo": {"inicio": inicio.isoformat(), "fim": fim.isoformat(), "dias": (fim - inicio).days + 1},
        "atividade": [{"tipo": label, "registros": by_kind.get(k, 0), "empresas": len(companies_by_kind[k])} for k, label in ACTIVITY],
        "empresas_contatadas": len(contacted),
        "conversao": conversion,
        "funil_entradas": [{"etapa": STAGE_LABEL.get(k, k), "key": k, "empresas": v} for k, v in entered.most_common() if k],
        "perdas": {"total": len(lost_ids), "motivos": [{"motivo": m, "empresas": n} for m, n in reasons.most_common(10)]},
        "sinais_novos": {"total": len(signals),
                         "por_fonte": [{"fonte": f, "sinais": n} for f, n in Counter(o.source_name for o in signals).most_common()]},
        "empresas_novas": sum(1 for c in db.query(Company.created_at).all() if _in(c[0], a, b)),
        "tarefas": {"criadas": sum(1 for t in tasks if _in(t.created_at, a, b)),
                    "concluidas": sum(1 for t in tasks if t.done and _in(t.done_at, a, b)),
                    "em_aberto": sum(1 for t in tasks if not t.done),
                    "atrasadas_agora": sum(1 for t in tasks if not t.done and t.due_at and as_utc(t.due_at) < real_now)},
        "notas": ["Contagens do que está registrado no sistema; não há estimativas nem projeções.",
                  "Conversão: das empresas contatadas no período, quantas já tinham resposta, reunião, proposta ou contrato registrados até o fim do período."],
    }


def to_csv_rows(r: dict) -> list[list]:
    rows = [["secao", "item", "valor", "complemento"],
            ["periodo", "inicio", r["periodo"]["inicio"], ""], ["periodo", "fim", r["periodo"]["fim"], ""]]
    rows += [["atividade", x["tipo"], x["registros"], f"{x['empresas']} empresa(s)"] for x in r["atividade"]]
    rows += [["conversao", x["etapa"], x["empresas"], "" if x["pct_contatadas"] is None else f"{x['pct_contatadas']}%"] for x in r["conversao"]]
    rows += [["funil", x["etapa"], x["empresas"], "entradas no período"] for x in r["funil_entradas"]]
    rows += [["perdas", x["motivo"], x["empresas"], ""] for x in r["perdas"]["motivos"]]
    rows += [["sinais", x["fonte"], x["sinais"], ""] for x in r["sinais_novos"]["por_fonte"]]
    rows += [["empresas", "novas na base", r["empresas_novas"], ""]]
    rows += [["tarefas", k, v, ""] for k, v in r["tarefas"].items()]
    return rows
