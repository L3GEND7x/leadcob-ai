from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import Company, BusinessContact
from app.services.contact_targets import targets


def test_missing_channel_targets_and_duplicates():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        a = Company(name="Fixture A",cnpj="11222333000181",city="Manaus",state="AM",
                    registration_status="ATIVA",website="https://example.com")
        b = Company(name="Fixture duplicate",cnpj=a.cnpj,city="Manaus",state="AM",
                    registration_status="ATIVA",website=a.website)
        db.add_all([a,b]);db.commit()
        r=targets(db,"AM","Manaus","email")
        assert r["active_unique_cnpjs"]==1
        assert r["missing_channel"]==1
        assert r["ready_for_site_discovery"]==1
        assert r["items"][0]["company_id"]==a.id
        db.add(BusinessContact(company_id=b.id,kind="email",value="contato@example.com",
                               source_name="Fixture",status="a_verificar",department="geral"))
        db.commit()
        r=targets(db,"AM","Manaus","email")
        assert r["with_channel"]==1
        assert r["with_verified_channel"]==0
        assert r["missing_channel"]==0
        assert targets(db,"AM","Manaus","phone")["missing_channel"]==1
    engine.dispose()
