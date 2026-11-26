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
                registry_updated_at=datetime.now(timezone.utc),cnae_main="4631100",legal_nature="206-2 Sociedade Empresária Limitada"))
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


def test_qualification_requires_corporate_registry_and_public_evidence_url():
    from datetime import datetime, timezone
    from app.db.models import BusinessContact, Opportunity
    from app.services.cnpj import _dv, WEIGHTS_1, WEIGHTS_2
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for i, nature, url in [
            (1, "206-2 Sociedade Empresária Limitada", "https://example.test/vagas"),
            (2, "206-2 Sociedade Empresária Limitada", "http://127.0.0.1/private"),
            (3, "213-5 Empresário Individual", "https://example.test/vagas"),
            (4, None, "https://example.test/vagas"),
            (5, "206-2 Sociedade Empresária Limitada", "not-a-url"),
        ]:
            base = f"{i:012d}"
            first = _dv(base, WEIGHTS_1)
            db.add(Company(id=i, name=f"Fixture {i}", cnpj=base+first+_dv(base+first, WEIGHTS_2),
                state="AM", city="Manaus", registration_status="ATIVA", registry_source="Fixture",
                registry_updated_at=datetime.now(timezone.utc), cnae_main="4631100", legal_nature=nature))
            db.flush()
            db.add(BusinessContact(company_id=i, kind="email", value="financeiro@example.test",
                status="verificado", source_name="Fixture", source_url="https://example.test/contato", department="geral"))
            db.add(Opportunity(company_id=i, kind="hiring", title="Fixture",
                status="qualified", is_verified=True, source_name="Fixture", source_url=url))
        db.commit()
        result = qualification(db, "AM", "Manaus")
        rows = {x["company_id"]: x for x in result["items"]}
        assert rows[1]["tier"] == "priority_review"
        for i in (2, 5):
            assert rows[i]["tier"] == "contactable_prospect"
            assert rows[i]["evidence_ids"] == []
        for i in (3, 4):
            assert rows[i]["tier"] == "registry_review"
            assert rows[i]["channels"] == rows[i]["evidence_ids"] == []
            assert rows[i]["name"] == "Cadastro empresarial a revisar"
        assert result["contact_coverage"]["active_sourced_cnpjs"] == 3
        assert result["contact_coverage"]["with_verified_channel"] == 3
    engine.dispose()


def test_priority_requires_contact_provenance_and_current_deadline():
    from datetime import datetime, timedelta, timezone
    from app.db.models import BusinessContact, Opportunity
    now = datetime.now(timezone.utc)
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        c=Company(name='Fixture PJ',cnpj='11222333000181',state='AM',city='Manaus',
            registration_status='ATIVA',registry_source='Fixture',registry_updated_at=now,
            cnae_main='4631100',legal_nature='2062')
        db.add(c);db.flush()
        contact=BusinessContact(company_id=c.id,kind='email',value='contato@example.test',
            status='verificado',source_name='Fixture')
        evidence=Opportunity(company_id=c.id,kind='hiring',title='Fixture',source_name='Fixture',
            source_url='https://example.test/vaga',status='qualified',is_verified=True,deadline=now+timedelta(days=1))
        db.add_all([contact,evidence]);db.commit()
        def row():
            return qualification(db,'AM','Manaus')['items'][0]
        assert row()['tier']=='evidence_contact_needed'
        for source in ('http://127.0.0.1/', 'not-a-url'):
            contact.source_url=source;db.commit()
            assert row()['tier']=='evidence_contact_needed'
        contact.source_url='https://example.test/contato';db.commit()
        assert row()['tier']=='priority_review'
        assert row()['verified_sourced_channels']==['email']
        evidence.deadline=now-timedelta(seconds=1);db.commit()
        assert row()['tier']=='contactable_prospect' and row()['evidence_ids']==[]
        contact.source_name='Demonstração';evidence.deadline=None;db.commit()
        assert row()['tier']=='evidence_contact_needed'
    engine.dispose()


def test_global_duplicate_cannot_escape_qualification_or_opt_out():
    from datetime import datetime, timezone
    common=dict(cnpj='11222333000181',registration_status='ATIVA',registry_source='Fixture',
        registry_updated_at=datetime.now(timezone.utc),cnae_main='4631100',legal_nature='2062')
    engine=create_engine('sqlite://');Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Company(name='Fixture AM',city='Manaus',state='AM',**common))
        peer=Company(name='Fixture SP',city='São Paulo',state='SP',**common)
        db.add(peer);db.commit()
        assert qualification(db,'AM','Manaus')['counts']=={'prospect_research':1}
        peer.registration_status='BAIXADA';db.commit()
        assert qualification(db,'AM','Manaus')['counts']=={'registry_review':1}
        peer.registration_status='ATIVA';peer.legal_nature='2135 Empresário Individual';db.commit()
        assert qualification(db,'AM','Manaus')['items'][0]['name']=='Cadastro empresarial a revisar'
        peer.legal_nature='2062';peer.pipeline_stage='nao_contatar';db.commit()
        assert qualification(db,'AM','Manaus')['items']==[]
    engine.dispose()
