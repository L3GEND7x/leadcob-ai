"""LGPD retention for institutional business contacts.

Disabled until the owner configures contact_retention_days.
Only invalid contacts or contacts of suppressed companies are anonymized.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from app.db.database import SessionLocal
from app.db.models import BusinessContact, Setting, Suppression


def _stamp(v):
    return v.replace(tzinfo=timezone.utc) if v and v.tzinfo is None else v


def anonymized_value(value: str) -> str:
    return "anon:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def retention_days(db) -> int | None:
    row = db.get(Setting, "geral")
    value = (row.value or {}) if row else {}
    days = value.get("contact_retention_days")
    return int(days) if isinstance(days, int) and days > 0 else None


def run_retention(db, now: datetime | None = None) -> dict:
    days = retention_days(db)
    if not days:
        return {"enabled": False, "days": None, "anonymized": 0}

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    suppressed = {
        s.company_id: _stamp(s.created_at)
        for s in db.query(Suppression).filter(Suppression.company_id.isnot(None)).all()
    }
    changed = 0
    rows = db.query(BusinessContact).all()
    for contact in rows:
        if contact.value.startswith("anon:"):
            continue
        invalid_old = contact.status == "invalido" and _stamp(contact.checked_at or contact.created_at) <= cutoff
        suppressed_at = suppressed.get(contact.company_id)
        suppressed_old = bool(suppressed_at and suppressed_at <= cutoff)
        if not (invalid_old or suppressed_old):
            continue
        contact.value = anonymized_value(contact.value)
        contact.source_url = None
        contact.department = "anonimizado"
        contact.status = "invalido"
        contact.checked_at = now
        changed += 1
    db.commit()
    return {"enabled": True, "days": days, "anonymized": changed}


def main():
    with SessionLocal() as db:
        result = run_retention(db)
    print(
        "Retenção desativada: configure contact_retention_days."
        if not result["enabled"]
        else f"Retenção concluída: {result['anonymized']} contato(s) anonimizado(s)."
    )


if __name__ == "__main__":
    main()
