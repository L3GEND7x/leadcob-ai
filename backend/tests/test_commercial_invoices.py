from uuid import uuid4
from datetime import datetime,timezone,timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.core.security import password_hash
from app.db.database import SessionLocal
from app.db.models import Organization,CommercialPlan,CommercialInvoice,AuditLog


def test_billing_ledger(monkeypatch):
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
        path=f'/api/owner/commercial/organizations/{oid}/invoices'
        try:
            assert c.get(path).status_code==401
            login=c.post('/api/auth/login',json={'username':settings.admin_username,'password':'owner-long-password-test'})
            assert login.status_code==200
            headers={'Origin':'http://testserver','X-CSRF-Token':login.json()['csrf_token']}
            payload=dict(plan_id=pid,period_start='2026-11-01',period_end='2026-12-01',due_date='2026-11-10')
            assert c.post(path,json=payload).status_code==403
            r=c.post(path,json=payload,headers=headers)
            assert r.status_code==201,r.text
            row=r.json()
            assert row['amount_cents']==2700 and row['status']=='open'
            assert c.post(path,json=payload,headers=headers).json()['id']==row['id']
            assert c.post(path,json=payload|{'period_start':'2026-11-15','period_end':'2026-12-15'},headers=headers).status_code==409
            settle=path+'/'+str(row['id'])+'/settle'
            payment=dict(amount_cents=2700,payment_reference=code,paid_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat())
            assert c.post(settle,json=payment|{'amount_cents':2699},headers=headers).status_code==422
            r=c.post(settle,json=payment,headers=headers)
            assert r.status_code==200,r.text
            assert r.json()['status']=='paid'
            assert c.post(settle,json=payment,headers=headers).status_code==200
            assert c.post(settle,json=payment|{'payment_reference':code+'-other'},headers=headers).status_code==409
            assert c.post(path+'/'+str(row['id'])+'/void',headers=headers).status_code==409
            assert len(c.get(path).json())==1
        finally:
            with SessionLocal() as db:
                ids=[x.id for x in db.query(CommercialInvoice).filter_by(organization_id=oid)]
                db.query(AuditLog).filter(AuditLog.entity_type=='commercial_invoice',AuditLog.entity_id.in_(ids)).delete(synchronize_session=False)
                db.query(CommercialInvoice).filter_by(organization_id=oid).delete()
                db.query(Organization).filter_by(id=oid).delete()
                db.query(CommercialPlan).filter_by(id=pid).delete()
                db.commit()
