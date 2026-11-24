"""Private city metrics must never confuse records, CNPJs, and channels."""
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.core import security
from app.core.config import settings
from app.db.database import Base, get_db
from app.db.models import Company, BusinessContact, Suppression
from app.services.cnpj import _dv, WEIGHTS_1, WEIGHTS_2
from app.services.contact_readiness import contactability


def cnpj(i):
    base=f"{i:012d}"
    one=_dv(base, WEIGHTS_1)
    return base+one+_dv(base+one, WEIGHTS_2)


def test_cnpj_contactability_and_owner_endpoint(tmp_path,monkeypatch):
    engine=create_engine(f"sqlite:///{tmp_path/'readiness.sqlite'}",
                         connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine)
    def override_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db]=override_db
    monkeypatch.setattr(security,"SessionLocal",factory)
    monkeypatch.setattr(settings,"admin_password_hash",security.password_hash("fixture-strong-owner-password"))
    monkeypatch.setattr(settings,"admin_username","fixture-"+uuid4().hex)
    monkeypatch.setattr(settings,"app_env","development")
    monkeypatch.setattr(settings,"public_url","")
    corp="Sociedade Empresária Limitada"
    companies=[
        (1,1,"ATIVA",corp,"https://alpha.example"),
        (2,1,"ATIVA",corp,"https://alpha.example"),
        (3,3,"ATIVA",corp,"https://beta.example"),
        (4,3,"ATIVA",corp,"https://other.example"),
        (5,5,"ATIVA","Empresário Individual",""),
        (6,6,"ATIVA",corp,""),
        (7,6,"ATIVA",corp,""),
        (8,8,"BAIXADA",corp,""),
        (9,9,"ATIVA",corp,""),
        (10,10,"ATIVA",corp,""),
    ]
    with factory() as db:
        for id_,num,status,nature,site in companies:
            db.add(Company(id=id_,cnpj=cnpj(num),name=f"Empresa {id_}",state="AM",
                city="Manaus",registration_status=status,legal_nature=nature,website=site))
        db.flush()
        db.add(Suppression(company_id=7,reason="opt-out de CNPJ duplicado"))
        contact_rows=[
            (1,"email","contato@alpha.example","verificado","https://alpha.example/contato"),
            (2,"email","contato@alpha.example","verificado",None),
            (1,"email","pessoa.nome@alpha.example","verificado","https://alpha.example"),
            (3,"phone","92999999999","a_verificar","https://beta.example"),
            (4,"linkedin","https://www.linkedin.com/company/beta","verificado","https://beta.example"),
            (10,"phone","92988888888","verificado",None),
            (5,"email","contato@individual.example","verificado","https://individual.example"),
            (6,"email","financeiro@bloqueada.example","verificado","https://bloqueada.example"),
            (8,"email","contato@baixada.example","verificado","https://baixada.example"),
        ]
        for company_id,kind,value,status,source_url in contact_rows:
            db.add(BusinessContact(company_id=company_id,kind=kind,value=value,
                status=status,source_name="Fixture",source_url=source_url))
        db.commit()
        result=contactability(db)
        assert result["valid_unique_cnpjs"]==6
        assert result["active_unique_cnpjs"]==5
        assert result["active_corporate_cnpjs"]==4
        assert result["with_consistent_registered_site"]==1
        assert result["with_conflicting_sites"]==1
        assert result["with_any_direct_channel"]==3
        assert result["with_verified_direct_channel"]==3
        assert result["with_verified_sourced_direct_channel"]==2
        assert result["without_direct_channel"]==1
        assert result["channels"]["email"]["registered"]==1
        assert result["channels"]["phone"]=={"registered":2,"verified":1,
            "with_source_url":1,"verified_with_source_url":0}
        assert result["channels"]["linkedin"]["verified_with_source_url"]==1
        assert "contato@alpha" not in str(result)
        assert "92999999999" not in str(result)
    client=TestClient(app)
    try:
        assert client.get("/api/contacts/contactability").status_code==401
        login=client.post("/api/auth/login",json={
            "username":settings.admin_username,"password":"fixture-strong-owner-password"})
        assert login.status_code==200,login.text
        response=client.get("/api/contacts/contactability?uf=AM&city=Manaus")
        assert response.status_code==200,response.text
        assert response.json()["active_corporate_cnpjs"]==4
        assert "contato@alpha" not in response.text
        assert "92999999999" not in response.text
        assert client.get("/api/contacts/contactability?uf=AM&city=%20").status_code==422
    finally:
        client.close()
        app.dependency_overrides.pop(get_db,None)
        engine.dispose()
