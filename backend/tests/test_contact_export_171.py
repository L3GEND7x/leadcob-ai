"""Authenticated owner-only CSV export: active CNPJs, suppression, provenance and formula safety."""
import csv
import io
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


def cnpj(i):
    b=f"{i:012d}"
    a=_dv(b,WEIGHTS_1)
    return b+a+_dv(b+a,WEIGHTS_2)


def test_owner_export_is_bounded_private_and_cannot_execute_spreadsheet_formulas(tmp_path, monkeypatch):
    engine=create_engine(f"sqlite:///{tmp_path/'contact-export.sqlite'}",connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine)
    Session=sessionmaker(bind=engine)
    def override_db():
        with Session() as db:
            yield db
    app.dependency_overrides[get_db]=override_db
    monkeypatch.setattr(security,"SessionLocal",Session)
    monkeypatch.setattr(settings,"admin_password_hash",security.password_hash("owner-test-password-long"))
    monkeypatch.setattr(settings,"admin_username","owner-"+uuid4().hex)
    monkeypatch.setattr(settings,"app_env","development")
    monkeypatch.setattr(settings,"public_url","")
    with Session() as db:
        db.add_all([
            Company(id=1,cnpj=cnpj(1),name="=2+2 LTDA",state="AM",city="Manaus",registration_status="ATIVA",legal_nature="Sociedade Empresária Limitada"),
            Company(id=2,cnpj=cnpj(2),name="Empresa suprimida",state="AM",city="Manaus",registration_status="ATIVA"),
            Company(id=3,cnpj=cnpj(3),name="Empresa baixada",state="AM",city="Manaus",registration_status="BAIXADA",legal_nature="Sociedade Empresária Limitada"),
            Company(id=4,cnpj=cnpj(4),name="Empresa 4",state="AM",city="Manaus",registration_status="ATIVA",legal_nature="Sociedade Empresária Limitada"),
            Company(id=5,cnpj=cnpj(5),name="Empresário pessoa física",state="AM",city="Manaus",registration_status="ATIVA",legal_nature="Empresário Individual")])
        db.flush()
        db.add(Suppression(company_id=2,reason="opt-out"))
        for company,kind,value,status,url in [
            (1,"email","contato@example.com","verificado","https://example.com/contato"),
            (1,"phone","+559232324040","verificado","https://example.com"),
            (1,"email","joao.silva@example.com","verificado","https://example.com"),
            (2,"email","financeiro@bloqueada.com","verificado","https://bloqueada.com"),
            (3,"email","sac@baixada.com","verificado","https://baixada.com"),
            (4,"email","financeiro@empresa4.com","a_verificar","https://empresa4.com"),
            (4,"phone","559232324041","a_verificar",None),
            (5,"email","financeiro@pessoafisica.com","verificado","https://pessoafisica.com"),
        ]:
            db.add(BusinessContact(company_id=company,kind=kind,value=value,status=status,
                source_name="Teste institucional",source_url=url))
        db.commit()
    client=TestClient(app)
    url="/api/contacts/export.csv?uf=AM&city=Manaus"
    try:
        assert client.get(url).status_code==401
        login=client.post("/api/auth/login",json={
            "username":settings.admin_username,"password":"owner-test-password-long"})
        assert login.status_code==200,login.text
        response=client.get(url)
        assert response.status_code==200,response.text
        assert response.headers["x-exported-rows"]=="2"
        assert response.headers["x-has-more"]=="false"
        assert response.headers["x-next-offset"]==""
        assert "attachment" in response.headers["content-disposition"]
        assert response.headers["cache-control"]=="no-store"
        assert response.content.startswith(b"\xef\xbb\xbf")
        table=list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")),delimiter=";"))
        assert len(table)==3
        assert all(row[0]==cnpj(1) for row in table[1:])
        assert all(row[1].startswith("'=") for row in table[1:])
        assert any(row[5].startswith("'+5592") for row in table[1:])
        assert "joao.silva" not in response.text
        assert "bloqueada" not in response.text
        assert "baixada" not in response.text
        assert "pessoafisica" not in response.text
        more=client.get(url+"&status=todos")
        assert more.status_code==200,more.text
        assert more.headers["x-exported-rows"]=="3"
        assert "financeiro@empresa4.com" in more.text
        assert "559232324041" not in more.text  # unreviewed, untraceable phone
        assert client.get(url+"&status=errado").status_code==422
        assert client.get(url+"&limit=6000").status_code==422
    finally:
        client.close()
        app.dependency_overrides.pop(get_db,None)
        engine.dispose()



def test_export_pages_only_eligible_records_without_duplicates_and_verified_preferred():
    """Suppression and source filters must run BEFORE offset/limit, across all pages."""
    from sqlalchemy.orm import Session
    from app.services.contact_export import export_csv
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            Company(id=101,cnpj=cnpj(101),name="Alpha Ltda",state="AM",city="Manaus",
                    registration_status="ATIVA",legal_nature="Sociedade Limitada"),
            Company(id=102,cnpj=cnpj(101),name="Alpha filial",state="AM",city="Manaus",
                    registration_status="ATIVA",legal_nature="Sociedade Limitada"),
            Company(id=103,cnpj=cnpj(103),name="Opt out",state="AM",city="Manaus",
                    registration_status="ATIVA",legal_nature="Sociedade Limitada"),
            Company(id=104,cnpj=cnpj(103),name="Mesmo CNPJ suprimido",state="AM",city="Manaus",
                    registration_status="ATIVA",legal_nature="Sociedade Limitada"),
            Company(id=105,cnpj="00000000000000",name="CNPJ inválido",state="AM",city="Manaus",
                    registration_status="ATIVA",legal_nature="Sociedade Limitada"),
            Company(id=106,cnpj=cnpj(106),name="Beta Ltda",state="AM",city="Manaus",
                    registration_status="ATIVA",legal_nature="Sociedade Limitada"),
            Company(id=107,cnpj=cnpj(107),name="Empresário individual",state="AM",city="Manaus",
                    registration_status="ATIVA",legal_nature="Empresário Individual"),
        ])
        db.flush()
        db.add(Suppression(company_id=104,reason="opt-out da empresa duplicada"))
        for company,kind,value,status,url in [
            (101,"email","contato@alpha.example","a_verificar","https://alpha.example"),
            (102,"email","contato@alpha.example","verificado","https://alpha.example"),
            (102,"email","financeiro@alpha.example","verificado","https://alpha.example"),
            (102,"email","joao.silva@alpha.example","verificado","https://alpha.example"),
            (103,"email","contato@supprimida.example","verificado","https://supprimida.example"),
            (105,"email","contato@invalid.example","verificado","https://invalid.example"),
            (106,"email","sac@beta.example","verificado","https://beta.example"),
            (106,"email","vendas@beta.example","a_verificar",None),
            (107,"email","contato@individual.example","verificado","https://individual.example"),
        ]:
            db.add(BusinessContact(company_id=company,kind=kind,value=value,
                                   status=status,source_name="Fonte simulada",source_url=url))
        db.commit()
        data,n,has_more=export_csv(db,status="todos",limit=100)
        assert n==3 and has_more is False
        expected=list(csv.reader(io.StringIO(data.decode("utf-8-sig")),delimiter=";"))[1:]
        assert {row[5] for row in expected}=={
            "contato@alpha.example","financeiro@alpha.example","sac@beta.example"}
        assert next(row for row in expected if row[5]=="contato@alpha.example")[6]=="verificado"
        paged=[]
        for index in range(3):
            data,n,has_more=export_csv(db,status="todos",limit=1,offset=index)
            assert n==1
            assert has_more==(index<2)
            paged.extend(list(csv.reader(io.StringIO(data.decode("utf-8-sig")),delimiter=";"))[1:])
        assert paged==expected
        data,n,has_more=export_csv(db,status="todos",limit=1,offset=3)
        assert n==0 and has_more is False
    engine.dispose()
