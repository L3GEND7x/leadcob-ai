import json
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.api import routes_asaas_sandbox as hooks


def test_auth_and_event_validation():
    secret = "a" * 32
    assert hooks.authenticated(secret, secret)
    assert not hooks.authenticated("", "")
    assert not hooks.authenticated(secret, "wrong")
    payload = dict(id="evt_1", event="PAYMENT_RECEIVED", payment=dict(id="pay_1", value=1))
    assert hooks.parse_event(json.dumps(payload)) == ("evt_1", "PAYMENT_RECEIVED", "pay_1")
    with pytest.raises(HTTPException):
        hooks.parse_event(json.dumps(payload | {"payment": {"id": "../bad"}}))


def test_inbox_duplicate_and_conflict(monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE asaas_sandbox_events(event_id TEXT PRIMARY KEY,event_type TEXT NOT NULL,payment_id TEXT NOT NULL,received_at TEXT NOT NULL)"))
    monkeypatch.setattr(hooks, "SessionLocal", sessionmaker(bind=engine))
    assert hooks.store_event("evt_1", "PAYMENT_RECEIVED", "pay_1")["duplicate"] is False
    assert hooks.store_event("evt_1", "PAYMENT_RECEIVED", "pay_1")["duplicate"] is True
    with pytest.raises(HTTPException) as error:
        hooks.store_event("evt_1", "PAYMENT_RECEIVED", "pay_2")
    assert error.value.status_code == 409
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM asaas_sandbox_events")).scalar_one() == 1
