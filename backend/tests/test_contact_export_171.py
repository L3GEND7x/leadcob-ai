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
            Company(id=4,cnpj=cnpj(4),name="Empresa 4",state="AM",city="Manaus",registration_status="ATIVA")])
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
