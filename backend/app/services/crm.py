"""Regras do CRM de prospecção: etapas do funil, supressão (opt-out) e histórico."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from app.db.models import AuditLog, Company, Interaction, Setting, Suppression

MANAUS = timezone(timedelta(hours=-4))

STAGES = [
    ("identificada", "Empresa identificada"),
    ("em_pesquisa", "Em pesquisa"),
    ("qualificada", "Qualificada"),
    ("pronta_abordagem", "Pronta para abordagem"),
    ("primeiro_contato", "Primeiro contato realizado"),
    ("aguardando_resposta", "Aguardando resposta"),
    ("em_negociacao", "Em negociação comercial"),
    ("reuniao_agendada", "Reunião agendada"),
    ("proposta_enviada", "Proposta enviada"),
    ("cliente_conquistado", "Cliente conquistado"),
    ("perdido", "Perdido"),
    ("acompanhar_futuramente", "Acompanhar futuramente"),
    ("nao_contatar", "Não contatar"),
]
STAGE_LABEL = dict(STAGES)
NOT_APPROACHED = {"identificada", "em_pesquisa", "qualificada", "pronta_abordagem"}
CONTACTED = {"primeiro_contato", "aguardando_resposta", "em_negociacao", "reuniao_agendada", "proposta_enviada", "cliente_conquistado"}
CLOSED = {"cliente_conquistado", "perdido", "nao_contatar"}

INTERACTION_KINDS = {
    "contato": "Contato realizado", "resposta": "Resposta recebida", "reuniao": "Reunião",
    "proposta": "Proposta enviada", "contrato": "Contrato fechado", "nota": "Anotação",
    "follow_up": "Follow-up", "etapa": "Mudança de etapa", "sistema": "Registro do sistema",
}
OUTREACH_KINDS = {"contato", "follow_up", "proposta"}   # ações que alcançam a empresa
CHANNELS = {"email", "telefone", "whatsapp", "presencial", "linkedin", "outro"}

DEFAULT_SETTINGS = {
    "ufs_atuacao": [],            # vazio = Brasil inteiro
    "dias_entre_contatos": 7,     # trava contra abordagens repetidas
    "servico": "Cobrança e recuperação de crédito",
}


_CLOCK: datetime | None = None


def now() -> datetime:
    """Hora dos registros do CRM. Normalmente é a hora atual; ao reaplicar ações gravadas na página
    publicada, `clock()` fixa a hora original de cada ação para o histórico não mudar a cada atualização."""
    return _CLOCK or datetime.now(timezone.utc)


@contextmanager
def clock(at: datetime):
    global _CLOCK
    _CLOCK = as_utc(at)
    try:
        yield
    finally:
        _CLOCK = None


def stage_of(c: Company) -> str:
    return c.pipeline_stage or "identificada"


def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def get_settings(db) -> dict:
    row = db.get(Setting, "geral")
    return {**DEFAULT_SETTINGS, **((row.value if row else None) or {})}


def suppression_for(db, c: Company) -> Suppression | None:
    q = db.query(Suppression)
    if c.cnpj:
        hit = q.filter(Suppression.cnpj == c.cnpj).first()
        if hit:
            return hit
    return q.filter(Suppression.company_id == c.id).first()


def blocked_reason(db, c: Company) -> str | None:
    if stage_of(c) == "nao_contatar":
        return "Empresa marcada como 'Não contatar'."
    s = suppression_for(db, c)
    if s:
        return f"Empresa na lista de supressão desde {as_utc(s.created_at).astimezone(MANAUS):%d/%m/%Y}" + (f": {s.reason}" if s.reason else ".")
    return None


def last_outreach(c: Company) -> datetime | None:
    times = [as_utc(i.happened_at) for i in c.interactions if i.kind in OUTREACH_KINDS]
    return max(times) if times else None


def audit(db, event: str, entity_type: str, entity_id: int | None, details: dict):
    db.add(AuditLog(event=event, entity_type=entity_type, entity_id=entity_id, details=details))


def log_interaction(db, c: Company, kind: str, summary: str, channel: str | None = None,
                    outcome: str | None = None, happened_at: datetime | None = None) -> Interaction:
    it = Interaction(company_id=c.id, kind=kind, channel=channel, summary=summary, outcome=outcome,
                     happened_at=happened_at or now())
    db.add(it)
    return it


def change_stage(db, c: Company, new: str, reason: str | None = None):
    old = stage_of(c)
    if new == old:
        return
    c.pipeline_stage, c.stage_updated_at = new, now()
    log_interaction(db, c, "etapa", f"{STAGE_LABEL.get(old, old)} → {STAGE_LABEL.get(new, new)}" + (f" ({reason})" if reason else ""))
    audit(db, "stage_changed", "company", c.id, {"from": old, "to": new, "reason": reason})
    if new == "nao_contatar" and not suppression_for(db, c):
        db.add(Suppression(cnpj=c.cnpj, company_id=c.id, company_name=c.name, created_at=now(),
                           reason=reason or "Marcada como 'Não contatar' no CRM"))
