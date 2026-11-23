from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import (Company, Organization, AccountUser, WorkspaceSuppression, Suppression,
    WorkspaceProspectImport, WorkspaceLead, WorkspaceRegistryQueryQuota)
from app.core.account_access import AccessDenied, Principal
from app.services import workspace_registry_search as service, workspace_leads
from app.services.cnpj import _dv, WEIGHTS_1, WEIGHTS_2

def key(i):
    base=f"{i:012d}"
    first=_dv(base,WEIGHTS_1)
    return base+first+_dv(base+first,WEIGHTS_2)

def test_metering_and_secure_crm_import(monkeypatch):
    def authorize(db,token,org,permission,csrf=None):
        if token!=str(org) or (permission=="write" and csrf!="csrf"):
            raise AccessDenied()
        return Principal(org,org,"member")
    monkeypatch.setattr(service,"authorize",authorize)
    monkeypatch.setattr(workspace_leads,"authorize",authorize)
    monkeypatch.setattr(service,"check_subscription",lambda *args: None)
    monkeypatch.setattr(service.settings,"workspace_registry_search_enabled",True)
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Organization(id=i,name=f"Org {i}",slug=f"org-{i}",active=True) for i in (1,2)])
        db.add_all([AccountUser(id=i,email=f"usr{i}@example.test",password_hash="test",active=True) for i in (1,2)])
        for i in (1,2,3,4):
            db.add(Company(id=i,cnpj=key(i),name=f"Fixture {i} LTDA",state="AM",city="Manaus",
                cnae_main="4631100",legal_nature="Sociedade Empresária Limitada",
                registration_status="ATIVA",registry_source="Receita Federal — dados abertos 2026-10",
                registry_updated_at=datetime.now(timezone.utc)))
        db.add(WorkspaceSuppression(organization_id=1,cnpj=key(2),reason="Opt out"))
        db.add(Suppression(company_id=3,cnpj=key(3),reason="Opt out global"))
        db.commit()
        now=datetime(2026,11,23,15,tzinfo=timezone.utc)
        with pytest.raises(AccessDenied):
            service.consume_quota(db,"2",1,"csrf",now)
        for i in range(30):
            assert service.consume_quota(db,"1",1,"csrf",now)==i+1
        db.commit()
        with pytest.raises(HTTPException) as exc:
            service.consume_quota(db,"1",1,"csrf",now)
        assert exc.value.status_code==429
        db.rollback()
        assert service.consume_quota(db,"2",2,"csrf",now)==1
        assert service.consume_quota(db,"1",1,"csrf",now.replace(hour=16))==1
        db.commit()
        first=service.import_prospect(db,"1",1,"csrf",key(1))
        db.commit()
        assert first["cnpj"]==key(1)
        assert db.scalar(select(WorkspaceLead.organization_id).where(WorkspaceLead.id==first["lead_id"]))==1
        assert db.get(WorkspaceProspectImport,(1,key(1))).lead_id==first["lead_id"]
        for cnpj in (key(1),key(2),key(3)):
            with pytest.raises(HTTPException) as exc:
                service.import_prospect(db,"1",1,"csrf",cnpj)
            assert exc.value.status_code==409
            db.rollback()
        assert service.import_prospect(db,"2",2,"csrf",key(2))["cnpj"]==key(2)
        db.commit()
        with pytest.raises(AccessDenied):
            service.import_prospect(db,"2",1,"csrf",key(4))
        db.rollback()
        assert db.scalar(select(WorkspaceLead.id).where(WorkspaceLead.organization_id==1))==first["lead_id"]
    engine.dispose()
