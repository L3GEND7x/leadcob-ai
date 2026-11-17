from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.core.security import password_hash
from app.db.database import SessionLocal
from app.db.models import CommercialPlan, AuditLog


def test_owner_plan_catalog(monkeypatch):
    monkeypatch.setattr(settings,'admin_password_hash',password_hash('owner-long-password-test'))
    monkeypatch.setattr(settings,'admin_username','owner-'+uuid4().hex)
    monkeypatch.setattr(settings,'public_url','')
    code='test-'+uuid4().hex
    payload=dict(code=code,name='Plano de teste',monthly_price_cents=9900,max_members=3,
                 max_leads=100,max_contacts=200,max_tasks=100,max_portfolios=3,max_titles=1000)
    path='/api/owner/commercial/plans'
    with TestClient(app) as c:
        assert c.get(path).status_code==401
        login=c.post('/api/auth/login',json={'username':settings.admin_username,'password':'owner-long-password-test'})
        assert login.status_code==200
        headers={'Origin':'http://testserver','X-CSRF-Token':login.json()['csrf_token']}
        try:
            assert c.post(path,json=payload).status_code==403
            assert c.post(path,json=payload|{'monthly_price_cents':99.5},headers=headers).status_code==422
            assert c.post(path,json=payload|{'max_members':0},headers=headers).status_code==422
            r=c.post(path,json=payload,headers=headers)
            assert r.status_code==201,r.text
            data=r.json()
            pid=data['id']
            assert data['monthly_price_cents']==9900 and data['currency']=='BRL'
            assert data['active'] is False
            assert c.post(path,json=payload,headers=headers).status_code==409
            assert c.patch(path+f'/{pid}',json={'active':True},headers=headers).json()['active'] is True
            assert c.patch(path+f'/{pid}',json={'active':True,'monthly_price_cents':1},headers=headers).status_code==422
            assert any(x['id']==pid for x in c.get(path).json())
        finally:
            with SessionLocal() as db:
                row=db.query(CommercialPlan).filter_by(code=code).first()
                if row:
                    db.query(AuditLog).filter_by(entity_type='commercial_plan',entity_id=row.id).delete()
                    db.delete(row)
                    db.commit()
