"""Financial workspace operations. Caller owns transaction; never accesses legacy tables."""
from datetime import date
from decimal import Decimal, InvalidOperation
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.account_access import authorize
from app.db.models import WorkspacePortfolio, WorkspacePortfolioTitle

CENT = Decimal('0.01')
MAX_AMOUNT = Decimal('99999999999999.99')


class PortfolioNotFound(Exception):
    pass


def _date(value: str):
    if not isinstance(value, str):
        raise ValueError('Expected ISO date')
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError('Expected ISO date')
    return parsed


def _money(value: Decimal | str):
    if not isinstance(value, (Decimal, str)):
        raise ValueError('Use Decimal or decimal string')
    try:
        number = Decimal(value)
        if not number.is_finite() or not 0 < number <= MAX_AMOUNT or number != number.quantize(CENT):
            raise ValueError('Invalid amount')
        return number.quantize(CENT)
    except InvalidOperation as exc:
        raise ValueError('Invalid amount') from exc


def _portfolio(db, organization_id, portfolio_id):
    item = db.scalar(select(WorkspacePortfolio).where(
        WorkspacePortfolio.organization_id == organization_id, WorkspacePortfolio.id == portfolio_id))
    if item is None:
        raise PortfolioNotFound()
    return item


def list_portfolios(db: Session, token: str, organization_id: int, *, limit: int = 100, offset: int = 0):
    principal = authorize(db, token, organization_id, 'read')
    if not 1 <= limit <= 250 or offset < 0:
        raise ValueError('Invalid pagination')
    return list(db.scalars(select(WorkspacePortfolio)
        .where(WorkspacePortfolio.organization_id == principal.organization_id)
        .order_by(WorkspacePortfolio.id.desc()).offset(offset).limit(limit)))


def create_portfolio(db: Session, token: str, organization_id: int, csrf: str, *, name: str, reference_date: str):
    principal = authorize(db, token, organization_id, 'write', csrf=csrf)
    _date(reference_date)
    if not name.strip() or len(name) > 160:
        raise ValueError('Invalid name')
    item = WorkspacePortfolio(organization_id=principal.organization_id, name=name.strip(),
                              reference_date=reference_date)
    db.add(item)
    db.flush()
    return item


def add_title(db: Session, token: str, organization_id: int, csrf: str, portfolio_id: int,
              *, reference: str, amount: Decimal | str, due_date: str):
    principal = authorize(db, token, organization_id, 'write', csrf=csrf)
    portfolio = _portfolio(db, principal.organization_id, portfolio_id)
    _date(due_date)
    amount = _money(amount)
    if not reference.strip() or len(reference) > 80:
        raise ValueError('Invalid reference')
    reference = reference.strip()
    if db.scalar(select(WorkspacePortfolioTitle.id).where(
            WorkspacePortfolioTitle.portfolio_id == portfolio.id,
            WorkspacePortfolioTitle.reference == reference)) is not None:
        raise ValueError('Duplicate reference')
    item = WorkspacePortfolioTitle(portfolio_id=portfolio.id, reference=reference,
                                   amount=amount, due_date=due_date)
    db.add(item)
    db.flush()
    return item


def list_titles(db: Session, token: str, organization_id: int, portfolio_id: int, *,
                limit: int = 100, offset: int = 0):
    principal = authorize(db, token, organization_id, 'read')
    portfolio = _portfolio(db, principal.organization_id, portfolio_id)
    if not 1 <= limit <= 250 or offset < 0:
        raise ValueError('Invalid pagination')
    return list(db.scalars(select(WorkspacePortfolioTitle)
        .where(WorkspacePortfolioTitle.portfolio_id == portfolio.id)
        .order_by(WorkspacePortfolioTitle.id).offset(offset).limit(limit)))


def summarize_portfolio(db: Session, token: str, organization_id: int, portfolio_id: int, *, as_of: str):
    principal = authorize(db, token, organization_id, 'read')
    portfolio = _portfolio(db, principal.organization_id, portfolio_id)
    cutoff = _date(as_of)
    total = paid = overdue = current = Decimal('0.00')
    count = 0
    for item in db.scalars(select(WorkspacePortfolioTitle)
                           .where(WorkspacePortfolioTitle.portfolio_id == portfolio.id)):
        count += 1
        total += item.amount
        if item.paid_date and _date(item.paid_date) <= cutoff:
            paid += item.amount
        elif _date(item.due_date) < cutoff:
            overdue += item.amount
        else:
            current += item.amount
    return dict(count=count, total=total, paid=paid, overdue=overdue, current=current,
                outstanding=overdue + current, as_of=as_of)
