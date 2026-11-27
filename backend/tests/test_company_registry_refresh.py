import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import Company, AuditLog, BusinessContact
from app.api import routes


@pytest.fixture
def db():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_refresh_updates_registry_without_collecting_contacts_or_resetting_crm(db, monkeypatch):
    company = Company(name='Cadastro manual', cnpj='11222333000181', notes='Preservar',
                      website='https://example.test', pipeline_stage='nao_contatar')
    db.add(company); db.commit()
    monkeypatch.setattr(routes, '_lookup_or_http_error', lambda cnpj: dict(
        cnpj=cnpj, source='Fixture pública', razao_social='Empresa sintética LTDA',
        situacao_cadastral='ATIVA', natureza_juridica='2062', municipio='MANAUS', uf='AM',
        cnae_principal='4631100', email='pessoal@example.test', telefone='000000000'))
    result = routes.enrich_company(company.id, db)
    db.refresh(company)
    assert result['name'] == 'Empresa sintética LTDA'
    assert company.registration_status == 'ATIVA' and company.legal_nature == '2062'
    assert company.registry_updated_at and 'Fixture pública' in company.registry_source
    assert company.notes == 'Preservar' and company.pipeline_stage == 'nao_contatar'
    assert company.website == 'https://example.test' and company.institutional_email is None
    assert db.query(BusinessContact).count() == 0
    event = db.query(AuditLog).filter_by(event='company_registry_refreshed').one()
    assert event.entity_id == company.id and event.details['source'] == 'Fixture pública'
    assert set(event.details) <= {'source', 'actor'}


def test_registry_failure_keeps_previous_data_and_does_not_log_success(db, monkeypatch):
    company = Company(name='Cadastro preservado', cnpj='11222333000181')
    db.add(company); db.commit()
    def fail(cnpj):
        raise HTTPException(502, 'Consulta indisponível')
    monkeypatch.setattr(routes, '_lookup_or_http_error', fail)
    with pytest.raises(HTTPException):
        routes.enrich_company(company.id, db)
    db.refresh(company)
    assert company.name == 'Cadastro preservado' and company.registry_updated_at is None
    assert db.query(AuditLog).count() == 0
