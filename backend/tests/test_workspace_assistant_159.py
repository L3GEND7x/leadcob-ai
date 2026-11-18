from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import Organization, AccountUser, CommercialPlan, CommercialSubscription, WorkspaceAssistantBudgetLock, WorkspaceAssistantExchange
from app.core.account_access import AccessDenied, Principal
from app.services import workspace_assistant as service
import openai

def test_private_history_and_reservation(monkeypatch):
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now=datetime.now(timezone.utc)
    for k,v in dict(workspace_assistant_enabled=True,workspace_assistant_monthly_budget_usd=1.0,
        openai_api_key="fixture",openai_model="fixture",openai_input_usd_per_million=1.0,
        openai_output_usd_per_million=2.0).items():
        monkeypatch.setattr(service.settings,k,v)
    def auth(db,token,org,permission,csrf=None):
        allowed={"a":(1,1),"b":(1,2),"c":(2,3)}
        scope,user=allowed.get(token,(0,0))
        if org!=scope or (permission=="write" and csrf!="test"):
            raise AccessDenied()
        return Principal(user,scope,"member")
    monkeypatch.setattr(service,"authorize",auth)
    calls=[]
    class Client:
        def __init__(self,**kwargs):
            self.responses=self
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def create(self,**kwargs):
            calls.append(kwargs)
            assert kwargs["store"] is False
            assert "tools" not in kwargs
            return SimpleNamespace(status="completed",output_text="Resposta fixture",
                usage=SimpleNamespace(input_tokens=10,output_tokens=2))
    monkeypatch.setattr(openai,"OpenAI",Client)
    with Session(engine) as db:
        db.add_all([Organization(id=1,name="A",slug="a",active=True),Organization(id=2,name="B",slug="b",active=True)])
        db.add_all([AccountUser(id=i,email=f"user{i}@example.test",password_hash="fixture",active=True) for i in (1,2,3)])
        db.add(CommercialPlan(id=1,code="fixture",name="Fixture",monthly_price_cents=2700,
            max_members=3,max_leads=10,max_contacts=10,max_tasks=10,max_portfolios=10,max_titles=10,active=True))
        db.add_all([CommercialSubscription(organization_id=i,plan_id=1,starts_at=now-timedelta(days=1),
            ends_at=now+timedelta(days=1),status="active") for i in (1,2)])
        db.add(WorkspaceAssistantBudgetLock(id=1))
        db.commit()
        rid=str(uuid4())
        result=service.generate(db,"a",1,"test",rid,"Pergunta fixture")
        assert result["status"]=="completed"
        assert db.get(WorkspaceAssistantExchange,rid).charged_micro_usd==14
        assert len(service.history(db,"a",1))==1
        assert service.history(db,"b",1)==[]
        assert service.history(db,"c",2)==[]
        with pytest.raises(AccessDenied):
            service.history(db,"c",1)
        with pytest.raises(HTTPException) as exc:
            service.generate(db,"a",1,"test",rid,"Repetição")
        assert exc.value.status_code==409
        db.rollback()
        monkeypatch.setattr(service.settings,"workspace_assistant_monthly_budget_usd",0.000001)
        with pytest.raises(HTTPException) as exc:
            service.generate(db,"c",2,"test",str(uuid4()),"Pergunta")
        assert exc.value.status_code==429
        assert len(calls)==1
    engine.dispose()
