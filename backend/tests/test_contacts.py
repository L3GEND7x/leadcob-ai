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


def test_discovery_channels_filters_counts_and_suppression(monkeypatch):
    from app.collectors import site_contacts
    ensure_schema()
    with SessionLocal() as db:
        company = Company(name="CHANNELS TEST", state="AM", city="Manaus", website="https://empresa.com.br")
        db.add(company)
        db.commit()
        cid = company.id
    monkeypatch.setattr(site_contacts, "discover", lambda _: {
        "emails": [], "pages_read": ["https://empresa.com.br"], "notes": [],
        "channels": [
            {"kind": "phone", "value": "559232324040", "source_url": "https://empresa.com.br"},
            {"kind": "linkedin", "value": "https://linkedin.com/company/empresa", "source_url": "https://empresa.com.br"},
        ],
    })
    client = TestClient(app)
    try:
        first = client.post(f"/api/contacts/discover/{cid}")
        assert first.status_code == 200
        assert first.json()["added"] == 2
        assert client.post(f"/api/contacts/discover/{cid}").json()["added"] == 0
        params = {"company_id": cid, "uf": "am", "city": "Manaus"}
        data = client.get("/api/contacts", params=params).json()
        assert data["total"] == 2
        assert data["companies_by_channel"] == {"phone": 1, "linkedin": 1}
        assert client.get("/api/contacts", params={**params, "uf": "SP"}).json()["total"] == 0
        phone = next(x for x in data["items"] if x["kind"] == "phone")
        client.patch(f"/api/contacts/{phone['id']}/verify?status=invalido")
        assert client.get("/api/contacts", params=params).json()["companies_by_channel"] == {"linkedin": 1}
        with SessionLocal() as db:
            db.add(Suppression(company_id=cid, reason="Não contatar"))
            db.commit()
        assert client.get("/api/contacts", params=params).json()["companies_by_channel"] == {}
        assert client.post(f"/api/contacts/discover/{cid}").status_code == 403
    finally:
        with SessionLocal() as db:
            db.query(Suppression).filter_by(company_id=cid).delete()
            db.query(BusinessContact).filter_by(company_id=cid).delete()
            db.query(Company).filter_by(id=cid).delete()
            db.commit()


def test_social_and_whatsapp_validation():
    assert clean("whatsapp", "(92) 99999-9999") == "5592999999999"
    assert clean("linkedin", "https://linkedin.com/company/empresa") == "https://www.linkedin.com/company/empresa/"
    for url in ("https://linkedin.com/in/pessoa", "https://linkedin.com.evil.test/company/empresa"):
        with pytest.raises(HTTPException):
            clean("linkedin", url)


def test_domain_search_without_provider_offers_public_search(monkeypatch):
    from app.core.config import settings
    from urllib.parse import urlparse, parse_qs
    monkeypatch.setattr(settings, "brave_search_api_key", "")
    ensure_schema()
    with SessionLocal() as db:
        company = Company(name="BUSCA & CONTATO TESTE")
        db.add(company)
        db.commit()
        cid = company.id
    client = TestClient(app)
    try:
        response = client.post(f"/api/contacts/domain-search/{cid}")
        assert response.status_code == 200
        data = response.json()
        assert data["automatic_available"] is False
        assert data["items"] == []
        url = urlparse(data["search_url"])
        assert url.netloc == "duckduckgo.com"
        assert "BUSCA & CONTATO TESTE" in parse_qs(url.query)["q"][0]
        assert "API_KEY" not in data["note"]
        with SessionLocal() as db:
            db.add(Suppression(company_id=cid, reason="Não contatar"))
            db.commit()
        assert client.post(f"/api/contacts/domain-search/{cid}").status_code == 404
    finally:
        with SessionLocal() as db:
            db.query(Suppression).filter_by(company_id=cid).delete()
            db.query(Company).filter_by(id=cid).delete()
            db.commit()
