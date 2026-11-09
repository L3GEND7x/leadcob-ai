from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Integer, Float, ForeignKey, Boolean, JSON, UniqueConstraint
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
    opportunities = relationship("Opportunity", back_populates="company")
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
