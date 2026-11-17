from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import Organization, CommercialPlan, CommercialSubscription, WorkspaceLead
from app.core.config import settings
from app.services.commercial_entitlements import enforce, usage


def test_entitlements(monkeypatch):
    monkeypatch.setattr(settings,'commercial_entitlements_enabled',True)
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        a=Organization(name='A',slug='a',active=True)
        b=Organization(name='B',slug='b',active=True)
        plan=CommercialPlan(code='test',name='Test',monthly_price_cents=2700,
            max_members=1,max_leads=1,max_contacts=0,max_tasks=1,max_portfolios=1,max_titles=1,active=True)
        db.add_all([a,b,plan])
        db.flush()
        now=datetime.now(timezone.utc)
        sub=CommercialSubscription(organization_id=a.id,plan_id=plan.id,
            starts_at=now-timedelta(days=1),ends_at=now+timedelta(days=1),status='active')
        db.add(sub)
        db.commit()
        enforce(db,a.id,'leads')
        db.add(WorkspaceLead(organization_id=a.id,name='Lead',notes='',stage='identified'))
        db.commit()
        assert usage(db,a.id)['leads']==1
        assert usage(db,b.id)['leads']==0
        for oid,resource,code in [(a.id,'leads',409),(a.id,'contacts',409),(b.id,'leads',402)]:
            with pytest.raises(HTTPException) as exc:
                enforce(db,oid,resource)
            assert exc.value.status_code==code
            db.rollback()
        sub.ends_at=now-timedelta(seconds=1)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            enforce(db,a.id)
        assert exc.value.status_code==402
        db.rollback()
        assert usage(db,a.id)['leads']==1
        monkeypatch.setattr(settings,'commercial_entitlements_enabled',False)
        enforce(db,b.id,'leads')
    engine.dispose()
