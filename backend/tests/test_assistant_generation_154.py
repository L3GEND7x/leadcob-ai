from types import SimpleNamespace
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import AssistantUsage, AssistantRequest, AuditLog
from app.api import routes_assistant as assistant
import openai
import pytest
from fastapi import HTTPException


def test_generation_probe(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    for key,value in {"openai_api_key":"fixture-key", "openai_model":"fixture-model",
                      "assistant_monthly_budget_usd":10.0,
                      "openai_input_usd_per_million":1.0,
                      "openai_output_usd_per_million":2.0}.items():
        monkeypatch.setattr(assistant.settings,key,value)
    calls=[]
    class Client:
        def __init__(self,**kwargs):
            assert kwargs["max_retries"]==0
            self.responses=self
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def create(self,**kwargs):
            calls.append(kwargs)
            assert kwargs == dict(model="fixture-model",input="Responda somente OK.",max_output_tokens=128,store=False)
            return SimpleNamespace(status="completed",output_text="OK",usage=SimpleNamespace(input_tokens=10,output_tokens=2))
    monkeypatch.setattr(openai,"OpenAI",Client)
    request=SimpleNamespace(state=SimpleNamespace(user="fixture-owner"))
    with Session(engine) as db:
        result=assistant.generation_check(request,db)
        assert result["generation_passed"] and not result["tools_tested"]
        assert db.scalar(select(AssistantUsage.charged_micro_usd))==14
        assert db.scalar(select(AssistantRequest.status))=="completed"
        assert db.scalar(select(AuditLog.event))=="assistant_generation_check"
        monkeypatch.setattr(assistant.settings,"assistant_monthly_budget_usd",0.000001)
        with pytest.raises(HTTPException) as exc:
            assistant.generation_check(request,db)
        assert exc.value.status_code==429
        assert len(calls)==1
    engine.dispose()
