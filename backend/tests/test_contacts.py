from fastapi.testclient import TestClient
from app.main import app
from app.db.database import SessionLocal, ensure_schema
from app.db.models import Company, BusinessContact, Suppression
from app.api.routes_contacts import clean
from fastapi import HTTPException
import pytest


def test_validation():
    assert clean('email', '  CONTATO@EXAMPLE.ORG ') == 'contato@example.org'
    with pytest.raises(HTTPException): clean('email', 'invalido')
    with pytest.raises(HTTPException): clean('website', 'javascript:alert(1)')


def test_sync_dedupe_and_suppression():
    ensure_schema()
    with SessionLocal() as db:
        c = Company(name='CONTATOS TESTE EMPRESA', cnpj=None, website='https://example.org', institutional_email='contato@example.org')
        db.add(c); db.commit(); cid=c.id
    client=TestClient(app)
    a=client.post('/api/contacts/sync').json()
    assert a['added'] >= 2
    assert client.post('/api/contacts/sync').json()['added'] == 0
    rows=client.get('/api/contacts',params={'q':'CONTATOS TESTE EMPRESA'}).json()
    assert rows['total']==2
    with SessionLocal() as db:
        db.add(Suppression(company_id=cid,reason='teste'));db.commit()
    assert client.get('/api/contacts',params={'q':'CONTATOS TESTE EMPRESA'}).json()['total']==0
    with SessionLocal() as db:
        db.query(Suppression).filter_by(company_id=cid).delete()
        db.query(BusinessContact).filter_by(company_id=cid).delete()
        db.query(Company).filter_by(id=cid).delete()
        db.commit()
