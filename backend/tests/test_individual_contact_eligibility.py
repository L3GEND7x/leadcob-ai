"""Legacy entry points must not bypass the corporate collection gates."""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import Company, BusinessContact, DomainCandidate
from app.api.routes_contacts import discover_from_site, enrich_contact_map, search_domain
from app.collectors import site_contacts
from app.services import domain_search


@pytest.fixture
def db():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def company(db, **changes):
    data = dict(name='Empresa de teste LTDA', cnpj='12345678000195',
                registration_status='ATIVA', legal_nature='Sociedade Empresária Limitada',
                website='https://example.org', city='Manaus', state='AM')
    data.update(changes)
    row = Company(**data)
    db.add(row); db.commit()
    return row


@pytest.mark.parametrize('action', [discover_from_site, enrich_contact_map, search_domain])
@pytest.mark.parametrize('changes,code', [
    ({'registration_status': 'BAIXADA'}, 422),
    ({'legal_nature': '2135 Empresário Individual'}, 422),
    ({'legal_nature': None}, 422),
    ({'cnpj': '12345678000190'}, 422),
    ({'cnae_main': '8291100'}, 422),
    ({'pipeline_stage': 'nao_contatar'}, 403),
])
def test_ineligible_never_calls_external_providers(db, monkeypatch, action, changes, code):
    row = company(db, **changes)
    def forbidden(*args, **kwargs):
        pytest.fail('An ineligible company reached an external provider')
    monkeypatch.setattr(site_contacts, 'discover', forbidden)
    monkeypatch.setattr(domain_search, 'search', forbidden)
    with pytest.raises(HTTPException) as error:
        action(row.id, db)
    assert error.value.status_code == code
    assert db.query(BusinessContact).count() == 0
    assert db.query(DomainCandidate).count() == 0


@pytest.mark.parametrize('action', [discover_from_site, enrich_contact_map, search_domain])
@pytest.mark.parametrize('changes,code', [
    ({'pipeline_stage': 'nao_contatar'}, 403),
    ({'registration_status': 'INAPTA'}, 422),
    ({'website': 'https://other.example.org'}, 409),
])
def test_duplicate_outside_city_blocks_individual_paths(db, monkeypatch, action, changes, code):
    row = company(db)
    company(db, name='Duplicata LTDA', cnpj='12.345.678/0001-95', city='Belém', state='PA', **changes)
    def forbidden(*args, **kwargs):
        pytest.fail('Conflicting duplicate reached external collection')
    monkeypatch.setattr(site_contacts, 'discover', forbidden)
    monkeypatch.setattr(domain_search, 'search', forbidden)
    with pytest.raises(HTTPException) as error:
        action(row.id, db)
    assert error.value.status_code == code
    assert db.query(BusinessContact).count() == 0


@pytest.mark.parametrize('action', [discover_from_site, enrich_contact_map])
def test_opt_out_during_site_read_prevents_contact_storage(db, monkeypatch, action):
    row = company(db)
    def fetch(website):
        row.pipeline_stage = 'nao_contatar'
        db.commit()
        return dict(emails=[{'email': 'contato@example.org', 'source_url': website}],
                    channels=[], pages_read=[website], notes=[])
    monkeypatch.setattr(site_contacts, 'discover', fetch)
    with pytest.raises(HTTPException) as error:
        action(row.id, db)
    assert error.value.status_code == 403
    assert db.query(BusinessContact).filter(BusinessContact.kind == 'email').count() == 0


@pytest.mark.parametrize('action', [enrich_contact_map, search_domain])
def test_opt_out_during_domain_search_discards_candidates(db, monkeypatch, action):
    from app.core.config import settings
    row = company(db, website=None)
    monkeypatch.setattr(settings, 'brave_search_api_key', 'test-only')
    def search(c, key):
        row.pipeline_stage = 'nao_contatar'
        db.commit()
        return [dict(website='https://example.org', source_url='https://example.org',
                     evidence='CNPJ publicado no site', status='cnpj_no_site')]
    monkeypatch.setattr(domain_search, 'search', search)
    with pytest.raises(HTTPException) as error:
        action(row.id, db)
    assert error.value.status_code == 403
    assert db.query(DomainCandidate).count() == 0
    assert db.query(BusinessContact).count() == 0
    assert db.get(Company, row.id).website is None
