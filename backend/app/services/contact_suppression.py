"""Fail-closed global opt-out across multiple Company records of the same CNPJ.

The owner can hold duplicate records with different formatting. Suppressing
either record or its explicit CNPJ blocks ALL matching contact endpoints.
No database mutation or external request is performed by these helpers.
"""
from sqlalchemy import func, select, or_
from app.db.models import Company, Suppression
from app.services.cnpj import clean_cnpj


def sql_cnpj(column):
    """Normalize familiar punctuation in SQL; supports alphanumeric CNPJ."""
    cleaned = func.upper(func.coalesce(column, ""))
    for mark in (".", "/", "-", " ", "\t", "(", ")"):
        cleaned = func.replace(cleaned, mark, "")
    return cleaned


def matching_suppression(db, company):
    """Return the matching opt-out row, including another record of the same CNPJ."""
    if company is None:
        return None
    value = clean_cnpj(company.cnpj)
    predicate = Suppression.company_id == company.id
    if value:
        predicate = or_(
            predicate,
            sql_cnpj(Suppression.cnpj) == value,
            sql_cnpj(Company.cnpj) == value,
        )
    return db.scalar(
        select(Suppression)
        .outerjoin(Company, Company.id == Suppression.company_id)
        .where(predicate)
        .order_by(Suppression.id)
        .limit(1)
    )


def is_suppressed(db, company):
    return company is None or matching_suppression(db, company) is not None


def suppression_keys(db):
    """Keys for collection queries; one suppressed row blocks all same-CNPJ rows."""
    blocked_ids = set(db.scalars(
        select(Suppression.company_id).where(Suppression.company_id.isnot(None))
    ))
    blocked_keys = {clean_cnpj(v) for v in db.scalars(
        select(Suppression.cnpj).where(Suppression.cnpj.isnot(None))
    ) if v}
    if blocked_ids:
        blocked_keys.update(
            clean_cnpj(v) for v in db.scalars(
                select(Company.cnpj).where(Company.id.in_(blocked_ids))
            ) if v
        )
    return blocked_ids, {k for k in blocked_keys if k}
