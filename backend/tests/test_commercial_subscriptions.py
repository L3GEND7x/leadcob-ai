from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.core.security import password_hash
from app.db.database import SessionLocal
from app.db.models import CommercialPlan,CommercialSubscription,Organization,AuditLog
from app.services.commercial_subscriptions import subscription_status


def test_subscription_dates():
    now=datetime.now(timezone.utc)
    row=SimpleNamespace(status='active',starts_at=now,ends_at=now+timedelta(days=30))
    assert subscription_status(None,now)=='unassigned'
    assert subscription_status(row,now-timedelta(seconds=1))=='scheduled'
    assert subscription_status(row,now)=='active'
    assert subscription_status(row,row.ends_at)=='expired'
    row.status='cancelled'
    assert subscription_status(row,now)=='cancelled'


def test_owner_subscription(monkeypatch):
    monkeypatch.setattr(settings,'admin_password_hash',password_hash('owner-long-password-test'))
    monkeypatch.setattr(settings,'admin_username','owner-'+uuid4().hex)
    monkeypatch.setattr(settings,'public_url','')
    code='test-'+uuid4().hex
    with TestClient(app) as c:
        with SessionLocal() as db:
            org=Organization(name='Test',slug=code,active=True)
            plan=CommercialPlan(code=code,name='Test',monthly_price_cents=2700,max_members=1,
                max_leads=500,max_contacts=1000,max_tasks=100,max_portfolios=2,max_titles=1000,active=True)
            db.add_all([org,plan])
            db.flush()
            oid,pid=org.id,plan.id
            db.commit()
        path=f'/api/owner/commercial/organizations/{oid}/subscription'
        try:
            assert c.get(path).status_code==401
            login=c.post('/api/auth/login',json={'username':settings.admin_username,'password':'owner-long-password-test'})
            assert login.status_code==200
            headers={'Origin':'http://testserver','X-CSRF-Token':login.json()['csrf_token']}
            assert c.get(path).json()['status']=='unassigned'
            now=datetime.now(timezone.utc)
            payload=dict(plan_id=pid,starts_at=now.isoformat(),ends_at=(now+timedelta(days=30)).isoformat())
            assert c.put(path,json=payload).status_code==403
            assert c.put(path,json=payload|{'ends_at':now.isoformat()},headers=headers).status_code==422
            result=c.put(path,json=payload,headers=headers)
            assert result.status_code==200,result.text
            assert result.json()['status']=='active'
            assert result.json()['plan']['monthly_price_cents']==2700
            assert c.post(path+'/cancel',headers=headers).json()['status']=='cancelled'
            assert c.get(path).json()['status']=='cancelled'
        finally:
            with SessionLocal() as db:
                db.query(CommercialSubscription).filter_by(organization_id=oid).delete()
                db.query(AuditLog).filter_by(entity_type='organization',entity_id=oid).delete()
                db.query(Organization).filter_by(id=oid).delete()
                db.query(CommercialPlan).filter_by(id=pid).delete()
                db.commit()
