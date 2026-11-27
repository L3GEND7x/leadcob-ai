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
        company = Company(name="CHANNELS TEST", cnpj="12345678000195", registration_status="ATIVA", legal_nature="Sociedade Empresária Limitada", state="AM", city="Manaus", website="https://empresa.com.br")
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
        company = Company(name="BUSCA & CONTATO TESTE", cnpj="12345678000195", registration_status="ATIVA", legal_nature="Sociedade Empresária Limitada")
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


def test_contactability_map_is_transparent_and_department_aware():
    from types import SimpleNamespace
    from app.services.contactability import build_map, department_from_email

    assert department_from_email("licitacao@prefeitura.gov.br") == "Licitações/Compras"
    assert department_from_email("financeiro@empresa.com.br") == "Financeiro"
    assert department_from_email("joao.silva@empresa.com.br") == "geral"

    company = SimpleNamespace(name="MUNICIPIO TESTE", website="https://teste.gov.br")
    contacts = [
        SimpleNamespace(id=1, kind="email", value="licitacao@teste.gov.br", status="verificado",
                        department="Licitações/Compras", source_name="site oficial", source_url="https://teste.gov.br"),
        SimpleNamespace(id=2, kind="phone", value="83999999999", status="a_verificar",
                        department="geral", source_name="site oficial", source_url="https://teste.gov.br"),
    ]
    opportunities = [SimpleNamespace(kind="public_procurement", status="review",
                                     title="recuperação de créditos tributários", description="", evidence="")]
    result = build_map(company, contacts, opportunities)
    assert result["score"] == 40
    assert result["label"] == "Média"
    assert result["recommended_departments"][0] == "Finanças"
    assert "Licitações/Compras" in result["departments_found"]
    assert "inadimplência" not in result["note"].lower()


def test_enrich_contact_map_finds_verified_domain_and_institutional_channels(monkeypatch):
    from app.core.config import settings
    from app.collectors import site_contacts
    from app.services import domain_search
    from app.db.models import DomainCandidate, Opportunity

    ensure_schema()
    monkeypatch.setattr(settings, "brave_search_api_key", "chave-de-teste")
    with SessionLocal() as db:
        company = Company(name="MUNICIPIO MAPA TESTE", cnpj="12345678000195", registration_status="ATIVA", legal_nature="Município", segment="Órgão público",
                          state="PB", city="Caraúbas")
        db.add(company); db.flush()
        db.add(Opportunity(company_id=company.id, kind="public_procurement", source_key="mapa-contato-teste",
                           title="Recuperação de créditos tributários", description="", evidence="",
                           source_name="Teste", status="review"))
        db.commit(); cid = company.id

    monkeypatch.setattr(domain_search, "search", lambda company, key: [{
        "website": "https://caraubas.pb.gov.br",
        "source_url": "https://search.example/result",
        "evidence": "CNPJ 12345678000195 encontrado na página inicial do domínio.",
        "status": "cnpj_no_site",
    }])
    monkeypatch.setattr(site_contacts, "discover", lambda website: {
        "domain": "caraubas.pb.gov.br",
        "pages_read": [website, website + "/contato"],
        "emails": [{"email": "licitacao@caraubas.pb.gov.br", "source_url": website + "/contato"}],
        "channels": [{"kind": "phone", "value": "8331428503", "source_url": website + "/contato"}],
        "notes": [],
    })

    client = TestClient(app)
    try:
        response = client.post(f"/api/contacts/enrich/{cid}")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["added"] >= 3
        assert data["automatic_site_search"] is True
        assert data["score"] > 0
        assert "Licitações/Compras" in data["departments_found"]
        assert data["recommended_departments"][0] == "Finanças"
        with SessionLocal() as db:
            company = db.get(Company, cid)
            assert company.website == "https://caraubas.pb.gov.br"
            email = db.query(BusinessContact).filter_by(company_id=cid, kind="email").one()
            assert email.department == "Licitações/Compras"
            website = db.query(BusinessContact).filter_by(company_id=cid, kind="website").one()
            assert website.status == "verificado"

        mapped = client.get(f"/api/contacts/map/{cid}")
        assert mapped.status_code == 200
        assert mapped.json()["channels_available"] >= 3
    finally:
        with SessionLocal() as db:
            db.query(DomainCandidate).filter_by(company_id=cid).delete()
            db.query(BusinessContact).filter_by(company_id=cid).delete()
            db.query(Opportunity).filter_by(company_id=cid).delete()
            db.query(Company).filter_by(id=cid).delete()
            db.commit()


def test_company_search_exposes_contactability():
    ensure_schema()
    with SessionLocal() as db:
        company = Company(name="CONTACTABILITY SEARCH TEST", cnpj="12345678000190", state="AM")
        db.add(company); db.flush()
        db.add(BusinessContact(company_id=company.id, kind="email", value="financeiro@example.org",
                               department="Financeiro", source_name="teste", status="verificado"))
        db.commit(); cid = company.id
    try:
        data = TestClient(app).get("/api/companies/search", params={"q": "CONTACTABILITY SEARCH TEST"}).json()
        item = next(x for x in data["items"] if x["id"] == cid)
        assert item["contactability"]["score"] == 25
        assert item["contactability"]["best_channel"] == "email"
    finally:
        with SessionLocal() as db:
            db.query(BusinessContact).filter_by(company_id=cid).delete()
            db.query(Company).filter_by(id=cid).delete()
            db.commit()


def test_public_contact_search_uses_natural_terms_and_functional_mailboxes():
    from types import SimpleNamespace
    from urllib.parse import urlparse, parse_qs
    from app.services.contactability import _search_url
    from app.collectors.site_contacts import _role_box, CONTACT_HINT
    company = SimpleNamespace(name="MUNICIPIO DE BIRIGUI", city="Birigui", state="SP", website=None)
    q = parse_qs(urlparse(_search_url(company, ["responsável por Licitações/Compras"])).query)["q"][0]
    assert "Prefeitura de BIRIGUI" in q
    assert "site:gov.br" in q
    assert "responsável por" not in q
    assert _role_box("licitacao") and _role_box("financas")
    assert not _role_box("joao.silva")
    assert CONTACT_HINT.search("/secretarias/financas")
