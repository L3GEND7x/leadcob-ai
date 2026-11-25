import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.api.routes_crm import search_companies
from app.db.database import Base
from app.db.models import Company, Suppression


@pytest.fixture
def db():
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            Company(name="A blocked",cnpj="11111111000111",state="AM",city="Manaus",cnae_main="4631100"),
            Company(name="B allowed",cnpj="22222222000122",state="AM",city="Manaus",cnae_main="4711300",cnae_secondary="1234631,4631100"),
            Company(name="C substring",state="AM",city="Manaus",cnae_main="4711300",cnae_secondary="1234631"),
            Company(name="D south",state="SP",city="São Paulo",cnae_main="4631100")])
        session.commit()
        session.add(Suppression(cnpj="11111111000111",reason="Opt-out"))
        session.commit()
        yield session
    engine.dispose()


def test_contradictory_region_does_not_broaden(db):
    result=search_companies(region="Norte",uf="SP",sort="name",page=1,per_page=10,db=db)
    assert result["total"]==0 and result["items"]==[]


def test_suppression_applied_before_pagination(db):
    first=search_companies(uf="AM",sort="name",page=1,per_page=1,db=db)
    second=search_companies(uf="AM",sort="name",page=2,per_page=1,db=db)
    assert first["total"]==second["total"]==2
    assert first["items"][0]["name"]=="B allowed"
    assert second["items"][0]["name"]=="C substring"


def test_cnae_boundary_and_validation(db):
    result=search_companies(uf="AM",cnae="4631",sort="name",page=1,per_page=10,db=db)
    assert [x["name"] for x in result["items"]]==["B allowed"]
    with pytest.raises(HTTPException) as exc:
        search_companies(uf="AM",cnae="abc",sort="name",page=1,per_page=10,db=db)
    assert exc.value.status_code==422
