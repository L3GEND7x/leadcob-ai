from app.services.lead_qualification import tier, qualification
from app.db.database import Base
from app.db.models import Company, Suppression
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_priority_requires_active_sourced_registry_and_verified_contact():
    assert tier(True,True,"atacado",[1],{"email"},{"email"})=="priority_review"
    assert tier(True,True,"atacado",[1],{"email"},set())=="evidence_contact_needed"
    assert tier(True,True,"atacado",[],{"email"},{"email"})=="contactable_prospect"
    assert tier(True,True,"atacado",[],set(),set())=="prospect_research"
    assert tier(False,True,"atacado",[1],{"email"},{"email"})=="registry_review"
    assert tier(True,False,"atacado",[1],{"email"},{"email"})=="registry_review"
    assert tier(True,True,"concorrente_cobranca",[1],{"email"},{"email"})=="special_route"


def test_scope_duplicates_and_opt_out():
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Company(name="A",cnpj="11222333000181",city="Manaus",state="AM"),
                    Company(name="A duplicate",cnpj="11222333000181",city="Manaus",state="AM"),
                    Company(name="Invalid",cnpj="00000000000000",city="Manaus",state="AM"),
                    Company(name="Other city",cnpj="11222333000181",city="Iranduba",state="AM")])
        db.commit()
        result=qualification(db,"AM","Manaus")
        assert result["unique_cnpjs"]==1
        assert result["counts"]=={"registry_review":1}
        assert qualification(db,"AM","Manaus",selected_tier="priority_review")["total"]==0
        assert qualification(db,"AM","Manaus",offset=1)["items"]==[]
    engine.dispose()
