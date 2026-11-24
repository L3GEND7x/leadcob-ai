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


def test_cached_profile_and_contact_filters_preserve_qualification(monkeypatch):
    from datetime import datetime, timezone
    from app.db.models import BusinessContact
    from app.services import lead_qualification as service
    from app.services.cnpj import _dv, WEIGHTS_1, WEIGHTS_2
    original=service.profile_for
    calls=[]
    def profile(code):
        calls.append(code)
        return original(code)
    monkeypatch.setattr(service,"profile_for",profile)
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for i in range(1,11):
            base=f"{i:012d}"
            first=_dv(base,WEIGHTS_1)
            db.add(Company(id=i,name=f"Fixture {i}",cnpj=base+first+_dv(base+first,WEIGHTS_2),
                state="AM",city="Manaus",registration_status="ATIVA",registry_source="Fixture",
                registry_updated_at=datetime.now(timezone.utc),cnae_main="4631100"))
        db.flush()
        for i,kind,value,status in [(1,"email","financeiro@example.test","verificado"),
                (1,"email","contato@example.test","a_verificar"),(2,"email","\t ","verificado"),
                (3,"phone"," ANON:123 ","verificado"),(4,"website","https://example.test","verificado"),
                (5,"phone","559232324040","invalido"),(6,"phone","559232324041","a_verificar"),
                (2,"email","joao.silva@example.test","verificado"),
                (3,"phone","not-a-phone","verificado"),
                (4,"linkedin","https://www.linkedin.com/in/individual","verificado"),
                (7,"linkedin","https://linkedin.com.example.test/company/fixture","verificado"),
                (8,"whatsapp","123","verificado"),
                (9,"instagram","https://instagram.com.example.test/fixture","verificado")]:
            db.add(BusinessContact(company_id=i,kind=kind,value=value,status=status,
                source_name="Fixture",department="geral"))
        db.commit()
        result=qualification(db,"AM","Manaus",limit=2)
        assert calls==["4631100"]
        assert result["unique_cnpjs"]==10
        assert result["counts"]=={"contactable_prospect":2,"prospect_research":8}
        assert result["contact_coverage"]["with_any_channel"]==2
        assert result["contact_coverage"]["with_verified_channel"]==1
        assert [x["company_id"] for x in result["items"]]==[1,6]
        assert result["items"][0]["channels"]==["email"]
        assert qualification(db,"AM","Manaus",selected_tier="contactable_prospect",offset=1,limit=1)["items"][0]["company_id"]==6
    engine.dispose()
