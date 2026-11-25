import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes_contacts import ReviewedSiteIn, register_reviewed_site
from app.db.database import Base
from app.db.models import Company, DomainCandidate, AuditLog, Suppression, BusinessContact
from app.services.contact_targets import targets


def payload(**overrides):
    values = dict(website="https://example.com", source_url="https://example.com/institucional",
                  evidence="CNPJ divulgado na página institucional", ownership_reviewed=True)
    values.update(overrides)
    return ReviewedSiteIn(**values)


def test_reviewed_site_requires_explicit_review_and_preserves_existing_site():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company=Company(name="Empresa teste",cnpj="11222333000181",state="AM",city="Manaus",
                        registration_status="ATIVA",legal_nature="Sociedade Empresária Limitada")
        db.add(company);db.commit()
        cid=company.id
        for invalid in (payload(ownership_reviewed=False), payload(website="http://localhost"),
                        payload(source_url="http://127.0.0.1")):
            with pytest.raises(HTTPException) as exc:
                register_reviewed_site(cid,invalid,db)
            assert exc.value.status_code == 422
        assert company.website is None
        result=register_reviewed_site(cid,payload(),db)
        assert result["external_check"] is False
        assert company.website == "https://example.com"
        assert db.query(DomainCandidate).one().source_url == "https://example.com/institucional"
        assert db.query(AuditLog).filter_by(event="domain_reviewed_manually").count()==1
        assert db.query(BusinessContact).count()==0
        assert targets(db,"AM","Manaus","email")["items"][0]["discovery_ready"]
        with pytest.raises(HTTPException) as exc:
            register_reviewed_site(cid,payload(website="https://other.example"),db)
        assert exc.value.status_code==409
        db.add(Suppression(company_id=cid,reason="opt-out"));db.commit()
        with pytest.raises(HTTPException) as exc:
            register_reviewed_site(cid,payload(),db)
        assert exc.value.status_code==403
    engine.dispose()


def test_reviewed_site_rejects_conflicting_duplicate():
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first=Company(name="Empresa teste",cnpj="11222333000181",state="AM",city="Manaus",
                      registration_status="ATIVA",legal_nature="Sociedade Empresária Limitada")
        duplicate=Company(name="Empresa duplicada",cnpj="11222333000181",state="AM",city="Manaus",
                          registration_status="BAIXADA",legal_nature="Sociedade Empresária Limitada")
        db.add_all([first,duplicate]);db.commit()
        with pytest.raises(HTTPException) as exc:
            register_reviewed_site(first.id,payload(),db)
        assert exc.value.status_code==422
        assert first.website is None and db.query(DomainCandidate).count()==0
    engine.dispose()
