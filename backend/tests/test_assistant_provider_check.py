from types import SimpleNamespace
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import AuditLog
from app.core.config import settings
from app.api.routes_assistant import provider_check
import openai
import pytest
from fastapi import HTTPException


def configure(monkeypatch):
    for key,value in dict(openai_api_key="fixture-secret",openai_model="fixture-model",
        assistant_monthly_budget_usd=10,openai_input_usd_per_million=1,
        openai_output_usd_per_million=2).items():
        monkeypatch.setattr(settings,key,value)


def test_provider_metadata_only(monkeypatch):
    configure(monkeypatch)
    calls=[]
    class Client:
        def __init__(self,**kwargs):
            assert kwargs["max_retries"]==0
            self.models=SimpleNamespace(retrieve=self.retrieve)
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def retrieve(self,model):
            calls.append(model)
            return SimpleNamespace(id=model)
    monkeypatch.setattr(openai,"OpenAI",Client)
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        result=provider_check(SimpleNamespace(),db)
        assert result["model_accessible"]
        assert not result["generation_tested"]
        assert calls==["fixture-model"]
        assert "fixture-secret" not in str(result)
        assert db.query(AuditLog).filter_by(event="assistant_provider_check").count()==1
        monkeypatch.setattr(settings,"openai_api_key","")
        with pytest.raises(HTTPException) as error:
            provider_check(SimpleNamespace(),db)
        assert error.value.status_code==503
        assert len(calls)==1
    engine.dispose()
