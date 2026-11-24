from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import Company, BusinessContact
from app.services.lead_qualification import qualification


def test_contact_coverage_is_deduplicated_and_unaffected_by_tier_filter():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        common = dict(cnpj="11222333000181", city="Manaus", state="AM",
                      registration_status="ATIVA", registry_source="Fixture",
                      registry_updated_at=datetime.now(timezone.utc), cnae_main="4631100", legal_nature="206-2 Sociedade Empresária Limitada")
        a = Company(name="Fixture A", **common)
        b = Company(name="Fixture duplicate", **common)
        db.add_all([a,b])
        db.flush()
        for company in (a,b):
            db.add(BusinessContact(company_id=company.id, kind="email",
                value="financeiro@example.com", source_name="Fixture", status="verificado",
                department="geral"))
        db.commit()
        result = qualification(db,"AM","Manaus",selected_tier="priority_review")
        assert result["unique_cnpjs"] == 1
        assert result["total"] == 0
        c = result["contact_coverage"]
        assert c["active_sourced_cnpjs"] == 1
        assert c["with_any_channel"] == 1
        assert c["with_verified_channel"] == 1
        assert c["without_any_channel"] == 0
        assert c["channels"]["email"] == {"available":1,"verified":1}
        assert c["channels"]["phone"] == {"available":0,"verified":0}
    engine.dispose()
