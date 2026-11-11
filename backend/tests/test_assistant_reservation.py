"""Conservative budget accounting around provider calls."""
from datetime import datetime, timezone
from uuid import uuid4

import openai
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models import AssistantRequest, AssistantUsage
from app.main import app


def test_refund_only_when_provider_was_never_called(monkeypatch):
    monkeypatch.setattr(settings, 'openai_api_key', 'test-only')
    monkeypatch.setattr(settings, 'openai_model', 'test-model')
    monkeypatch.setattr(settings, 'assistant_monthly_budget_usd', 100)
    monkeypatch.setattr(settings, 'openai_input_usd_per_million', 1)
    monkeypatch.setattr(settings, 'openai_output_usd_per_million', 1)
    month = datetime.now(timezone.utc).strftime('%Y-%m')

    class BeforeSend:
        def __init__(self, **kwargs):
            raise RuntimeError('client construction failed')

    with TestClient(app) as client:
        with SessionLocal() as db:
            row = db.get(AssistantUsage, month)
            baseline = row.charged_micro_usd if row else 0

        monkeypatch.setattr(openai, 'OpenAI', BeforeSend)
        before_id = str(uuid4())
        assert client.post('/api/assistant/messages', json={
            'request_id': before_id, 'message': 'Resumo'}).status_code == 200
        with SessionLocal() as db:
            request = db.get(AssistantRequest, before_id)
            assert request.status == 'failed'
            assert db.get(AssistantUsage, month).charged_micro_usd == baseline

        class UncertainSend:
            def __init__(self, **kwargs):
                self.responses = self

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def create(self, **kwargs):
                raise TimeoutError('response unknown')

        monkeypatch.setattr(openai, 'OpenAI', UncertainSend)
        uncertain_id = str(uuid4())
        assert client.post('/api/assistant/messages', json={
            'request_id': uncertain_id, 'message': 'Outra pergunta'}).status_code == 200
        with SessionLocal() as db:
            request = db.get(AssistantRequest, uncertain_id)
            assert request.status == 'failed'
            assert db.get(AssistantUsage, month).charged_micro_usd == baseline + request.reserved_micro_usd
