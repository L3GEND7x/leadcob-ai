from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, Text, DateTime, Integer, Float, ForeignKey, Boolean, JSON, UniqueConstraint, Numeric, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
def now(): return datetime.now(timezone.utc)
class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(220), index=True)
    cnpj: Mapped[str|None] = mapped_column(String(14), nullable=True, index=True) # string para suportar CNPJ alfanumérico
    segment: Mapped[str|None] = mapped_column(String(120), nullable=True)
    city: Mapped[str|None] = mapped_column(String(100), nullable=True)
    state: Mapped[str|None] = mapped_column(String(2), nullable=True)
    website: Mapped[str|None] = mapped_column(String(500), nullable=True)
    institutional_email: Mapped[str|None] = mapped_column(String(255), nullable=True)
    # v0.3 — dados cadastrais (Receita Federal). Só pessoa jurídica: sem sócios, e-mail ou telefone.
    trade_name: Mapped[str|None] = mapped_column(String(220), nullable=True)
    cnae_main: Mapped[str|None] = mapped_column(String(7), nullable=True, index=True)
    cnae_desc: Mapped[str|None] = mapped_column(String(255), nullable=True)
    cnae_secondary: Mapped[str|None] = mapped_column(Text, nullable=True)
    registration_status: Mapped[str|None] = mapped_column(String(30), nullable=True)
    company_size: Mapped[str|None] = mapped_column(String(40), nullable=True)
    legal_nature: Mapped[str|None] = mapped_column(String(160), nullable=True)
    capital_social: Mapped[float|None] = mapped_column(Float, nullable=True)
    opened_at: Mapped[str|None] = mapped_column(String(10), nullable=True)
    target_profile: Mapped[str|None] = mapped_column(String(40), nullable=True, index=True)
    registry_source: Mapped[str|None] = mapped_column(String(120), nullable=True)
    registry_updated_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # v0.5 — CRM de prospecção (valores informados pelo usuário; nada é inferido)
    pipeline_stage: Mapped[str|None] = mapped_column(String(30), nullable=True, index=True)
    stage_updated_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_action: Mapped[str|None] = mapped_column(Text, nullable=True)
    next_action_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    potential_value: Mapped[float|None] = mapped_column(Float, nullable=True)  # informado/validado pelo usuário
    lost_reason: Mapped[str|None] = mapped_column(Text, nullable=True)
    notes: Mapped[str|None] = mapped_column(Text, nullable=True)
    opportunities = relationship("Opportunity", back_populates="company")
    interactions = relationship("Interaction", back_populates="company", order_by="Interaction.happened_at")
    tasks = relationship("Task", back_populates="company", order_by="Task.due_at")
    business_contacts = relationship("BusinessContact", back_populates="company", order_by="BusinessContact.id")
class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True) # hiring | outsourcing | public_procurement
    source_key: Mapped[str|None] = mapped_column(String(180), nullable=True, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(250))
    description: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[str] = mapped_column(Text, default="")
    source_name: Mapped[str] = mapped_column(String(120), default="Cadastro manual")
    source_url: Mapped[str|None] = mapped_column(String(1000), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    score: Mapped[int] = mapped_column(Integer, default=0)
    score_reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="review", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # v0.2.1 — classificação de contratações públicas (nulos para outras frentes)
    relevance: Mapped[str|None] = mapped_column(String(20), nullable=True, index=True)  # alta | revisar
    relevance_reason: Mapped[str|None] = mapped_column(Text, nullable=True)
    opportunity_class: Mapped[str|None] = mapped_column(String(30), nullable=True, index=True)
    evidence_level: Mapped[str|None] = mapped_column(String(30), nullable=True)
    commercial_signal: Mapped[str|None] = mapped_column(String(30), nullable=True, index=True)
    deadline: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_value: Mapped[float|None] = mapped_column(Float, nullable=True)
    modality_name: Mapped[str|None] = mapped_column(String(80), nullable=True)
    origin_url: Mapped[str|None] = mapped_column(String(1000), nullable=True)
    company = relationship("Company", back_populates="opportunities")
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    event: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[int|None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class CaptureRun(Base):
    __tablename__ = "capture_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="running")
    records_seen: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)


class MarketSnapshot(Base):
    """Fotografia de mercado (ex.: DataJud por UF). Dado agregado, sem partes."""
    __tablename__ = "market_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(60), index=True)
    uf: Mapped[str] = mapped_column(String(2), index=True)
    period_start: Mapped[str] = mapped_column(String(10))
    period_end: Mapped[str] = mapped_column(String(10))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Interaction(Base):
    """Histórico comercial da empresa (contatos, respostas, reuniões, propostas, mudanças de etapa)."""
    __tablename__ = "interactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    channel: Mapped[str|None] = mapped_column(String(30), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    outcome: Mapped[str|None] = mapped_column(String(30), nullable=True)
    happened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    company = relationship("Company", back_populates="interactions")


class Task(Base):
    """Atividade comercial com prazo (follow-up, pesquisa, abordagem, envio de proposta...)."""
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int|None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(250))
    kind: Mapped[str] = mapped_column(String(30), default="follow_up")
    due_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    done_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    company = relationship("Company", back_populates="tasks")


class Suppression(Base):
    """Lista de supressão (opt-out): empresas que não devem ser contatadas."""
    __tablename__ = "suppressions"
    id: Mapped[int] = mapped_column(primary_key=True)
    cnpj: Mapped[str|None] = mapped_column(String(14), nullable=True, index=True)
    company_id: Mapped[int|None] = mapped_column(Integer, nullable=True, index=True)
    company_name: Mapped[str|None] = mapped_column(String(220), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Setting(Base):
    """Configurações do usuário (UFs de atuação, serviço oferecido, intervalo entre contatos...)."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BusinessContact(Base):
    """Canal institucional verificável; não armazena dados pessoais de sócios/funcionários."""
    __tablename__ = "business_contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # email | website | phone
    value: Mapped[str] = mapped_column(String(500))
    department: Mapped[str] = mapped_column(String(40), default="geral")
    source_name: Mapped[str] = mapped_column(String(120))
    source_url: Mapped[str|None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="a_verificar")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    checked_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    company = relationship("Company", back_populates="business_contacts")
    __table_args__ = (UniqueConstraint("company_id", "kind", "value", name="uq_business_contact"),)


class Portfolio(Base):
    """Carteira de títulos de um CLIENTE CONTRATANTE (inteligência de cobrança). Separada da prospecção.
    Guarda só o mínimo para análise: valor, vencimento, pagamento e referência do título — nada do devedor."""
    __tablename__ = "portfolios"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    client_company_id: Mapped[int|None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    reference_date: Mapped[str] = mapped_column(String(10))
    archived_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    import_key: Mapped[str|None] = mapped_column(String(64), nullable=True, unique=True)
    import_report: Mapped[dict|None] = mapped_column(JSON, nullable=True)
    source_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    items = relationship("PortfolioItem", back_populates="portfolio", cascade="all, delete-orphan")


class PortfolioItem(Base):
    __tablename__ = "portfolio_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    ref: Mapped[str|None] = mapped_column(String(80), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(16, 2))
    due_date: Mapped[str] = mapped_column(String(10))
    paid_date: Mapped[str|None] = mapped_column(String(10), nullable=True)
    debtor_type: Mapped[str|None] = mapped_column(String(2), nullable=True)  # PJ | PF (sem identificação)
    portfolio = relationship("Portfolio", back_populates="items")
    events = relationship("PortfolioEvent", back_populates="item", order_by="PortfolioEvent.id")


class LoginSession(Base):
    __tablename__ = 'login_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(120))
    csrf_token: Mapped[str] = mapped_column(String(80))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AssistantConversation(Base):
    __tablename__ = 'assistant_conversations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AssistantMessage(Base):
    __tablename__ = 'assistant_messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey('assistant_conversations.id'), index=True)
    role: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AssistantUsage(Base):
    __tablename__ = 'assistant_usage'
    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    charged_micro_usd: Mapped[int] = mapped_column(Integer, default=0)


class AssistantRequest(Base):
    __tablename__ = 'assistant_requests'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey('assistant_conversations.id'), index=True)
    status: Mapped[str] = mapped_column(String(20), default='running')
    month: Mapped[str] = mapped_column(String(7))
    reserved_micro_usd: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(120))
    input_price: Mapped[float] = mapped_column(Float)
    output_price: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AssistantAction(Base):
    __tablename__ = 'assistant_actions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey('assistant_conversations.id'), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result_id: Mapped[int|None] = mapped_column(Integer, nullable=True)


class PortfolioEvent(Base):
    __tablename__ = 'portfolio_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey('portfolio_items.id'), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # payment | discount | reversal
    amount: Mapped[float] = mapped_column(Numeric(16, 2))
    effective_date: Mapped[str] = mapped_column(String(10))
    reference: Mapped[str] = mapped_column(String(120))
    reversal_of: Mapped[int|None] = mapped_column(ForeignKey('portfolio_events.id'), nullable=True, unique=True)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    item = relationship('PortfolioItem', back_populates='events')


class DomainCandidate(Base):
    __tablename__ = 'domain_candidates'
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey('companies.id'), index=True)
    website: Mapped[str] = mapped_column(String(500))
    source_url: Mapped[str] = mapped_column(String(1000))
    evidence: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='a_verificar')
    checked_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint('company_id', 'website', name='uq_domain_company_site'),)


class Organization(Base):
    """Commercial account. No legacy data is exposed through this model."""
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AccountUser(Base):
    __tablename__ = "account_users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Membership(Base):
    __tablename__ = "memberships"
    user_id: Mapped[int] = mapped_column(ForeignKey("account_users.id"), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (CheckConstraint("role IN ('admin', 'member', 'viewer')", name="ck_membership_role"),)


class AccountSession(Base):
    __tablename__ = "account_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("account_users.id"), index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    csrf_token: Mapped[str] = mapped_column(String(80))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class WorkspaceLead(Base):
    """Private prospect records, never populated from the owner's private CRM."""
    __tablename__ = "workspace_leads"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(220))
    notes: Mapped[str] = mapped_column(Text, default="")
    stage: Mapped[str] = mapped_column(String(30), default="identified")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (CheckConstraint("stage IN ('identified', 'contacted', 'negotiation', 'won', 'lost')", name="ck_workspace_lead_stage"),)


class WorkspacePortfolio(Base):
    """Private financial portfolio; independent of the legacy owner's portfolio."""
    __tablename__ = "workspace_portfolios"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    reference_date: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WorkspacePortfolioTitle(Base):
    __tablename__ = "workspace_portfolio_titles"
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("workspace_portfolios.id"), index=True)
    reference: Mapped[str] = mapped_column(String(80))
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    due_date: Mapped[str] = mapped_column(String(10))
    paid_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    __table_args__ = (
        UniqueConstraint("portfolio_id", "reference", name="uq_workspace_title_reference"),
        CheckConstraint("amount > 0", name="ck_workspace_title_positive"),
    )


class WorkspaceTask(Base):
    __tablename__ = "workspace_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(250))
    due_date: Mapped[str] = mapped_column(String(10))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WorkspaceContact(Base):
    __tablename__ = "workspace_contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    cnpj: Mapped[str] = mapped_column(String(14))
    kind: Mapped[str] = mapped_column(String(20))
    value: Mapped[str] = mapped_column(String(500))
    source_url: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("organization_id", "cnpj", "kind", "value", name="uq_workspace_contact"),
        CheckConstraint("kind IN ('email', 'website', 'phone', 'whatsapp', 'linkedin', 'instagram', 'facebook')", name="ck_workspace_contact_kind"),
    )


class WorkspaceSuppression(Base):
    __tablename__ = "workspace_suppressions"
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    cnpj: Mapped[str] = mapped_column(String(14), primary_key=True)
    reason: Mapped[str] = mapped_column(String(250))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
