"""One opt-out is shared by all duplicate Company rows of the same CNPJ."""
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.core import security
from app.core.config import settings
from app.db.database import Base, get_db
from app.db.models import Company, BusinessContact, Suppression
from app.services.cnpj import _dv, WEIGHTS_1, WEIGHTS_2
from app.api.routes_contacts import is_blocked


def cnpj(n):
    base=f"{n:012d}"
    first=_dv(base,WEIGHTS_1)
    return base+first+_dv(base+first,WEIGHTS_2)


def test_opt_out_by_duplicate_id_hides_all_routes_and_blocks_discovery(tmp_path,monkeypatch):
    engine=create_engine(f"sqlite:///{tmp_path/'suppression.sqlite'}",
                         connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine)
    def get_test_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db]=get_test_db
    monkeypatch.setattr(security,"SessionLocal",factory)
    monkeypatch.setattr(settings,"admin_username","owner-"+uuid4().hex)
    monkeypatch.setattr(settings,"admin_password_hash",security.password_hash("fixture-owner-password-strong"))
    monkeypatch.setattr(settings,"app_env","development")
    monkeypatch.setattr(settings,"public_url","")
    key=cnpj(123)
    with factory() as db:
        db.add_all([
            Company(id=101,cnpj=key,name="EMPRESA SUPRIMIDA MATRIZ",state="AM",city="Manaus",
                registration_status="ATIVA",website="https://example.org"),
            Company(id=102,cnpj=key,name="EMPRESA SUPRIMIDA FILIAL",state="AM",city="Manaus",
                registration_status="ATIVA",website="https://example.org"),
            Company(id=103,cnpj=cnpj(103),name="EMPRESA NAO SUPRIMIDA",state="AM",city="Manaus",
                registration_status="ATIVA",website="https://example.net")])
        db.flush()
        db.add_all([
            BusinessContact(company_id=101,kind="email",value="financeiro@example.org",
                source_name="Fixture",status="verificado"),
            BusinessContact(company_id=102,kind="email",value="contato@example.org",
                source_name="Fixture",status="verificado"),
            BusinessContact(company_id=103,kind="email",value="sac@example.net",
                source_name="Fixture",status="verificado")])
        db.add(Suppression(company_id=101,reason="Não abordar este CNPJ"))
        db.commit()
        second_contact=db.scalar(select(BusinessContact).where(BusinessContact.company_id==102)).id
        assert is_blocked(db,db.get(Company,102))
        assert not is_blocked(db,db.get(Company,103))
    from app.collectors import site_contacts
    monkeypatch.setattr(site_contacts,"discover",
        lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError("Blocked CNPJ must not fetch a website")))
    client=TestClient(app)
    try:
        assert client.get("/api/contacts").status_code==401
        login=client.post("/api/auth/login",json={
            "username":settings.admin_username,"password":"fixture-owner-password-strong"})
        assert login.status_code==200,login.text
        hdr={"x-csrf-token":login.json()["csrf_token"],"origin":"http://testserver"}
        result=client.get("/api/contacts",params={"uf":"AM","city":"Manaus"})
        assert result.status_code==200,result.text
        data=result.json()
        assert data["total"]==1
        assert len(data["items"])==1
        assert data["items"][0]["company_id"]==103
        assert "contato@example.org" not in result.text
        assert data["companies_by_channel"]=={"email":1}
        payload={"company_id":102,"kind":"email","value":"comercial@example.org",
                 "source_name":"Fixture de origem institucional"}
        assert client.post("/api/contacts",json=payload,headers=hdr).status_code==403
        assert client.post("/api/contacts/discover/102",headers=hdr).status_code==403
        assert client.post("/api/contacts/enrich/102",headers=hdr).status_code==403
        assert client.post("/api/contacts/domain-search/102",headers=hdr).status_code==404
        assert client.get("/api/contacts/map/102").status_code==403
        assert client.patch(f"/api/contacts/{second_contact}/verify?status=verificado",
                            headers=hdr).status_code==403
        assert client.post("/api/contacts/sync",headers=hdr).status_code==200
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(BusinessContact).where(
                BusinessContact.company_id==102))==1
            db.query(Suppression).filter(Suppression.company_id==101).delete()
            db.add(Suppression(cnpj=key.lower(),reason="Opt-out pelo CNPJ com caixa diferente"))
            db.commit()
            assert is_blocked(db,db.get(Company,101))
            assert is_blocked(db,db.get(Company,102))
        data=client.get("/api/contacts").json()
        assert data["total"]==1
        assert data["items"][0]["company_id"]==103
        assert client.post("/api/contacts",json=payload,headers=hdr).status_code==403
    finally:
        client.close()
        app.dependency_overrides.pop(get_db,None)
        engine.dispose()
