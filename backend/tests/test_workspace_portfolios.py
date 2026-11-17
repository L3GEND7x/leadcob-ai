from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.account_access import AccessDenied, issue_session
from app.core.security import password_hash
from app.db.database import Base
from app.db.models import AccountUser, Membership, Organization
from app.services.workspace_portfolios import (
    PortfolioNotFound, add_title, create_portfolio, list_portfolios, list_titles, summarize_portfolio,
)


def test_portfolios_isolation_and_decimal_totals():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        a = Organization(name='Teste A', slug='a', active=True)
        b = Organization(name='Teste B', slug='b', active=True)
        u = AccountUser(email='a@example.org', password_hash=password_hash('password-test-long-a'), active=True)
        v = AccountUser(email='b@example.org', password_hash=password_hash('password-test-long-b'), active=True)
        db.add_all([a, b, u, v])
        db.flush()
        db.add_all([Membership(user_id=u.id, organization_id=a.id, role='member', active=True),
                    Membership(user_id=v.id, organization_id=b.id, role='admin', active=True)])
        db.commit()
        ta, ca = issue_session(db, u.email, 'password-test-long-a', a.id)
        tb, cb = issue_session(db, v.email, 'password-test-long-b', b.id)
        x = create_portfolio(db, ta, a.id, ca, name='A', reference_date='2026-11-01')
        y = create_portfolio(db, tb, b.id, cb, name='B', reference_date='2026-11-01')
        add_title(db, ta, a.id, ca, x.id, reference='T1', amount='0.10', due_date='2026-11-01')
        add_title(db, ta, a.id, ca, x.id, reference='T2', amount='0.20', due_date='2026-11-30')
        add_title(db, tb, b.id, cb, y.id, reference='T1', amount='999.99', due_date='2026-11-01')
        db.commit()
        assert [p.id for p in list_portfolios(db, ta, a.id)] == [x.id]
        assert len(list_titles(db, ta, a.id, x.id)) == 2
        result = summarize_portfolio(db, ta, a.id, x.id, as_of='2026-11-17')
        assert result['total'] == Decimal('0.30')
        assert result['outstanding'] == Decimal('0.30')
        assert result['overdue'] == Decimal('0.10')
        assert result['current'] == Decimal('0.20')
        with pytest.raises(PortfolioNotFound):
            list_titles(db, ta, a.id, y.id)
        with pytest.raises(PortfolioNotFound):
            summarize_portfolio(db, ta, a.id, y.id, as_of='2026-11-17')
        with pytest.raises(PortfolioNotFound):
            add_title(db, ta, a.id, ca, y.id, reference='INTRUSO', amount='1', due_date='2026-11-17')
        with pytest.raises(AccessDenied):
            list_portfolios(db, ta, b.id)
        with pytest.raises(ValueError):
            add_title(db, ta, a.id, ca, x.id, reference='T1', amount='1', due_date='2026-11-17')
        for invalid in ('NaN', 'Infinity', '-1', '0', '0.001', 0.1):
            with pytest.raises(ValueError):
                add_title(db, ta, a.id, ca, x.id, reference='bad', amount=invalid, due_date='2026-11-17')
        db.get(Membership, (v.id, b.id)).role = 'viewer'
        db.commit()
        assert len(list_titles(db, tb, b.id, y.id)) == 1
        with pytest.raises(AccessDenied):
            add_title(db, tb, b.id, cb, y.id, reference='T2', amount='1', due_date='2026-11-17')
    engine.dispose()
