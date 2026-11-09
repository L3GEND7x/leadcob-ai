from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

IS_SQLITE = settings.database_url.startswith("sqlite")
# timeout: espera até 30 s por um banco ocupado (ex.: captação gravando enquanto os agentes rodam)
connect_args = {"check_same_thread": False, "timeout": 30} if IS_SQLITE else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)

if IS_SQLITE:
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        # WAL deixa leituras e uma escrita acontecerem ao mesmo tempo
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
class Base(DeclarativeBase): pass
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()


# Colunas acrescentadas depois da v0.1. `create_all` não altera tabelas
# existentes, então bancos antigos recebem as colunas aqui (SQLite e PostgreSQL).
LATE_COLUMNS = {
    "companies": {
        "trade_name": "VARCHAR(220)", "cnae_main": "VARCHAR(7)", "cnae_desc": "VARCHAR(255)", "cnae_secondary": "TEXT",
        "registration_status": "VARCHAR(30)", "company_size": "VARCHAR(40)", "legal_nature": "VARCHAR(160)",
        "capital_social": "FLOAT", "opened_at": "VARCHAR(10)", "target_profile": "VARCHAR(40)",
        "registry_source": "VARCHAR(120)", "registry_updated_at": "TIMESTAMP",
        "pipeline_stage": "VARCHAR(30)", "stage_updated_at": "TIMESTAMP", "next_action": "TEXT",
        "next_action_at": "TIMESTAMP", "potential_value": "FLOAT", "lost_reason": "TEXT", "notes": "TEXT",
    },
    "opportunities": {
        "source_key": "VARCHAR(180)", "relevance": "VARCHAR(20)", "relevance_reason": "TEXT",
        "opportunity_class": "VARCHAR(30)", "evidence_level": "VARCHAR(30)", "commercial_signal": "VARCHAR(30)",
        "deadline": "TIMESTAMP", "estimated_value": "FLOAT", "modality_name": "VARCHAR(80)", "origin_url": "VARCHAR(1000)",
    }
}
def ensure_schema():
    from app.db import models  # noqa: F401 — registra todas as tabelas no metadata
    Base.metadata.create_all(bind=engine)
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in LATE_COLUMNS.items():
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_opportunities_source_key ON opportunities (source_key)"))
