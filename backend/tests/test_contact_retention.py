from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import AuditLog, BusinessContact, Company, Setting, Suppression
from app.jobs.contact_retention import run_retention


NOW = datetime(2026, 11, 27, 16, 0, tzinfo=timezone.utc)


def _database():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine


def _company(db, name, cnpj):
    row = Company(name=name, cnpj=cnpj)
    db.add(row)
    db.flush()
    return row


def _contact(db, company, value, *, status="a_verificar", age=90):
    stamp = NOW - timedelta(days=age)
    row = BusinessContact(
        company_id=company.id,
        kind="email",
        value=value,
        department="geral",
        source_name="site oficial",
        source_url="https://example.org/contato",
        status=status,
        created_at=stamp,
        checked_at=stamp,
    )
    db.add(row)
    db.flush()
    return row


def test_retention_is_disabled_without_an_approved_period():
    engine = _database()
    with Session(engine) as db:
        company = _company(db, "SEM POLITICA", "18054044000160")
        contact = _contact(db, company, "contato@example.org", status="invalido")
        db.commit()

        result = run_retention(db, now=NOW, apply=True)

        assert result == {
            "enabled": False,
            "apply": True,
            "days": None,
            "matched": 0,
            "anonymized": 0,
            "truncated": False,
            "next_after_id": None,
        }
        assert db.get(BusinessContact, contact.id).value == "contato@example.org"


def test_dry_run_and_apply_cover_invalid_and_duplicate_cnpj_suppressions():
    engine = _database()
    with Session(engine) as db:
        db.add(Setting(key="geral", value={"contact_retention_days": 30}))
        invalid_company = _company(db, "INVALIDA", "62806802000140")
        direct_suppressed = _company(db, "SUPRIMIDA", "34904187000170")
        duplicate_a = _company(db, "DUPLICADA A", "10.208.800/0001-56")
        duplicate_b = _company(db, "DUPLICADA B", "10208800000156")
        safe_company = _company(db, "PRESERVADA", "18718109000124")
        recent_suppressed = _company(db, "SUPRESSAO RECENTE", "04252011000110")

        candidates = [
            _contact(db, invalid_company, "invalido@example.org", status="invalido"),
            _contact(db, direct_suppressed, "direto@example.org"),
            _contact(db, duplicate_b, "duplicado@example.org"),
        ]
        safe = _contact(db, safe_company, "preservado@example.org")
        recent = _contact(db, recent_suppressed, "recente@example.org")
        db.add_all([
            Suppression(company_id=direct_suppressed.id, reason="opt-out", created_at=NOW - timedelta(days=31)),
            Suppression(company_id=duplicate_a.id, reason="duplicidade", created_at=NOW - timedelta(days=31)),
            Suppression(cnpj=recent_suppressed.cnpj, reason="recente", created_at=NOW - timedelta(days=5)),
        ])
        db.commit()

        preview = run_retention(db, now=NOW, max_items=10)
        assert preview["matched"] == 3
        assert preview["anonymized"] == 0
        assert all(not db.get(BusinessContact, row.id).value.startswith("anon:") for row in candidates)

        applied = run_retention(db, now=NOW, apply=True, max_items=10)
        assert applied["matched"] == applied["anonymized"] == 3
        assert applied["truncated"] is False
        for row in candidates:
            current = db.get(BusinessContact, row.id)
            assert current.value.startswith("anon:")
            assert current.source_url is None
            assert current.source_name == "política de retenção"
            assert current.department == "anonimizado"
        assert db.get(BusinessContact, safe.id).value == "preservado@example.org"
        assert db.get(BusinessContact, recent.id).value == "recente@example.org"

        audit = db.scalar(select(AuditLog).where(AuditLog.event == "contact_retention_applied"))
        assert audit.details["anonymized"] == 3
        assert "invalido@example.org" not in str(audit.details)


def test_retention_is_bounded_and_resumable_by_cursor():
    engine = _database()
    with Session(engine) as db:
        db.add(Setting(key="geral", value={"contact_retention_days": 1}))
        company = _company(db, "LOTE", "03577877000107")
        contacts = [
            _contact(db, company, f"invalido{i}@example.org", status="invalido", age=2)
            for i in range(3)
        ]
        db.commit()

        first = run_retention(db, now=NOW, apply=True, max_items=2)
        assert first["anonymized"] == 2
        assert first["truncated"] is True
        assert first["next_after_id"] == contacts[1].id

        second = run_retention(
            db,
            now=NOW,
            apply=True,
            max_items=2,
            after_id=first["next_after_id"],
        )
        assert second["anonymized"] == 1
        assert second["truncated"] is False
        assert all(db.get(BusinessContact, row.id).value.startswith("anon:") for row in contacts)
