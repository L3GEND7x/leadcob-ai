from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.main import app
from app.core.config import settings
from app.core.security import password_hash
from app.db.database import Base
from app.services.contact_discovery_queue import enqueue, claim, finish
from app.api.routes_contacts import list_discovery_jobs


def test_history():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first=enqueue(db,[10,20])
        second=enqueue(db,[30])
        item,company,token=claim(db)
        assert company==10
        finish(db,item,token,{'status':'completed','added':1})
        rows=list_discovery_jobs(limit=50,offset=0,db=db)
        assert [x['job_id'] for x in rows]==[second,first]
        assert rows[1]['total']==2 and rows[1]['completed']==1 and rows[1]['queued']==1
        assert list_discovery_jobs(limit=1,offset=1,db=db)[0]['job_id']==first
    engine.dispose()


def test_owner_page(monkeypatch):
    monkeypatch.setattr(settings,'admin_password_hash',password_hash('owner-test-password-long'))
    monkeypatch.setattr(settings,'admin_username','owner-'+uuid4().hex)
    with TestClient(app) as c:
        assert c.get('/owner/discovery').status_code==401
        assert c.get('/api/contacts/discovery-jobs').status_code==401
        login=c.post('/api/auth/login',json={'username':settings.admin_username,'password':'owner-test-password-long'})
        assert login.status_code==200
        page=c.get('/owner/discovery')
        assert page.status_code==200
        assert 'no-store' in page.headers['cache-control']
        assert 'progress' in page.text
        assert c.get('/static/discovery.js').status_code==200
        assert c.get('/api/contacts/discovery-jobs').status_code==200


def test_owner_browser_navigation_redirects_only_to_fixed_login_destinations(monkeypatch):
    monkeypatch.setattr(settings, "admin_password_hash", password_hash("owner-test-password-long"))
    monkeypatch.setattr(settings, "admin_username", "owner-"+uuid4().hex)
    with TestClient(app) as c:
        for page, target in (("/owner/discovery", "discovery"), ("/owner/commercial", "commercial")):
            response = c.get(page+"?next=https://example.test", headers={"Accept":"text/html"}, follow_redirects=False)
            assert response.status_code == 303
            assert response.headers["location"] == "/?next="+target
            assert response.headers["cache-control"] == "no-store"
            assert c.get(page, headers={"Accept":"application/json"}, follow_redirects=False).status_code == 401
        assert c.get("/api/contacts/discovery-jobs", headers={"Accept":"text/html"}, follow_redirects=False).status_code == 401
        assert c.get("/api/owner/commercial/readiness", headers={"Sec-Fetch-Mode":"navigate"}, follow_redirects=False).status_code == 401
