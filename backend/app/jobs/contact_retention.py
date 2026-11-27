"""Bounded retention for institutional contacts.

The command is a dry run unless ``--apply`` is supplied. Retention also stays
disabled until the owner configures ``contact_retention_days``.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from secrets import token_hex

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import aliased

from app.db.database import SessionLocal
from app.db.models import AuditLog, BusinessContact, Company, Suppression
from app.services.contact_suppression import sql_cnpj
from app.services.crm import get_settings


def configured_days(db) -> int | None:
    value = get_settings(db).get("contact_retention_days")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 1 <= value <= 3650 else None


def _candidate_statement(cutoff: datetime, after_id: int):
    suppressed_company = aliased(Company)
    company_cnpj = sql_cnpj(Company.cnpj)
    has_matching_suppression = exists(
        select(Suppression.id)
        .select_from(Suppression)
        .outerjoin(suppressed_company, suppressed_company.id == Suppression.company_id)
        .where(
            Suppression.created_at <= cutoff,
            or_(
                Suppression.company_id == Company.id,
                and_(
                    company_cnpj != "",
                    or_(
                        sql_cnpj(Suppression.cnpj) == company_cnpj,
                        sql_cnpj(suppressed_company.cnpj) == company_cnpj,
                    ),
                ),
            ),
        )
    )
    old_invalid = and_(
        BusinessContact.status == "invalido",
        func.coalesce(BusinessContact.checked_at, BusinessContact.created_at) <= cutoff,
    )
    return (
        select(BusinessContact)
        .join(Company, Company.id == BusinessContact.company_id)
        .where(
            BusinessContact.id > after_id,
            ~BusinessContact.value.like("anon:%"),
            or_(old_invalid, has_matching_suppression),
        )
        .order_by(BusinessContact.id)
    )


def run_retention(
    db,
    *,
    now: datetime | None = None,
    apply: bool = False,
    max_items: int = 500,
    after_id: int = 0,
) -> dict:
    if not 1 <= max_items <= 5000:
        raise ValueError("max_items must be between 1 and 5000")
    if after_id < 0:
        raise ValueError("after_id must be non-negative")

    days = configured_days(db)
    if days is None:
        return {
            "enabled": False,
            "apply": apply,
            "days": None,
            "matched": 0,
            "anonymized": 0,
            "truncated": False,
            "next_after_id": None,
        }

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    rows = list(db.scalars(_candidate_statement(cutoff, after_id).limit(max_items + 1)))
    truncated = len(rows) > max_items
    candidates = rows[:max_items]
    next_after_id = candidates[-1].id if truncated and candidates else None

    if apply and candidates:
        for contact in candidates:
            contact.value = "anon:" + token_hex(16)
            contact.department = "anonimizado"
            contact.source_name = "política de retenção"
            contact.source_url = None
            contact.status = "invalido"
            contact.checked_at = now
        db.add(AuditLog(
            event="contact_retention_applied",
            entity_type="business_contact",
            details={
                "days": days,
                "anonymized": len(candidates),
                "after_id": after_id,
                "next_after_id": next_after_id,
                "truncated": truncated,
            },
        ))
        db.commit()

    return {
        "enabled": True,
        "apply": apply,
        "days": days,
        "cutoff": cutoff.isoformat(),
        "matched": len(candidates),
        "anonymized": len(candidates) if apply else 0,
        "truncated": truncated,
        "next_after_id": next_after_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Anonimiza contatos institucionais conforme retenção aprovada.")
    parser.add_argument("--apply", action="store_true", help="Aplica as alterações; sem esta opção é somente prévia.")
    parser.add_argument("--max-items", type=int, default=500, help="Limite por execução (1 a 5000).")
    parser.add_argument("--after-id", type=int, default=0, help="Cursor para continuar um lote truncado.")
    args = parser.parse_args()
    with SessionLocal() as db:
        result = run_retention(db, apply=args.apply, max_items=args.max_items, after_id=args.after_id)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
