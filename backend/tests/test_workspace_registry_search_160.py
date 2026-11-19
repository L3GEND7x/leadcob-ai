from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import Company, WorkspaceContact, WorkspaceSuppression, Suppression
from app.core.account_access import Principal, AccessDenied
from app.services import workspace_registry_search as service
from app.services.cnpj import _dv, WEIGHTS_1, WEIGHTS_2

def key(i):
    base=f"{i:012d}"
    first=_dv(base,WEIGHTS_1)
    return base+first+_dv(base+first,WEIGHTS_2)

def test_regional_search_scope_and_projection(monkeypatch):
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    def auth(db,token,org,permission):
        if token!=str(org):
            raise AccessDenied()
        return Principal(org,org,"member")
    monkeypatch.setattr(service,"authorize",auth)
    monkeypatch.setattr(service,"check_subscription",lambda *args:None)
    monkeypatch.setattr(service.settings,"workspace_registry_search_enabled",True)
    def company(i,**overrides):
        values=dict(id=i,cnpj=key(i),name=f"Fixture {i} LTDA",state="AM",city="Manaus",
            cnae_main="4631100",legal_nature="Sociedade Empresária Limitada",registration_status="ATIVA",
            registry_source="Receita Federal — dados abertos 2026-10 (arquivos locais)",
            registry_updated_at=datetime.now(timezone.utc),notes="PRIVATE OWNER NOTE",
            institutional_email="private@example.test")
        values.update(overrides)
        return Company(**values)
    with Session(engine) as db:
        db.add_all([company(1),company(2),company(3,city="Iranduba"),company(4,legal_nature="2135"),
            company(5,registry_source="Manual"),company(6,registration_status="BAIXADA"),
            company(7,name="Pessoa 12345678901"),company(8),company(9,cnae_main="8513900")])
        db.add(WorkspaceSuppression(organization_id=1,cnpj=key(2),reason="opt out"))
        db.add(Suppression(company_id=8,cnpj=key(8),reason="opt out"))
        db.add(WorkspaceContact(organization_id=1,cnpj=key(1),kind="email",value="financeiro@example.test",source_url="https://example.test"))
        db.commit()
        a=service.search(db,"1",1,"AM","Manaus",segment="atacado")
        assert [x["cnpj"] for x in a["items"]]==[key(1)]
        assert a["items"][0]["private_channels"]==["email"]
        assert "PRIVATE OWNER NOTE" not in str(a) and "private@example.test" not in str(a)
        assert service.search(db,"2",2,"AM","Manaus",channel="email")["total"]==0
        assert service.search(db,"2",2,"AM","Manaus",segment="atacado")["total"]==2
        assert service.search(db,"1",1,"AM","Manaus",segment="educacao_privada")["total"]==1
        with pytest.raises(AccessDenied):
            service.search(db,"2",1,"AM","Manaus")
        monkeypatch.setattr(service.settings,"workspace_registry_search_enabled",False)
        with pytest.raises(HTTPException) as exc:
            service.search(db,"1",1,"AM","Manaus")
        assert exc.value.status_code==503
    engine.dispose()
