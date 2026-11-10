"""Regressions reproduced from the operational audit."""
from datetime import date
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.core.security import password_hash
from app.core.security import validate_configuration
from app.services import collection, negotiation
from app.collectors.site_contacts import discover
from app.db.database import SessionLocal, ensure_schema
from app.db.models import Company, Portfolio, PortfolioEvent, Task


def test_money_and_historical_balance():
    result = negotiation.simulate({'valor_original': 1000, 'vencimento': '2026-11-10',
                                   'data_base': '2026-11-10', 'parcelas': 3})
    assert sum(row['valor'] for row in result['cronograma']) == result['total_a_receber'] == 1000
    assert [row['valor'] for row in result['cronograma']] == [333.33, 333.33, 333.34]
    assert result['cronograma'][-1]['saldo'] == 0
    assert collection.parse_money('1.250', 'br') == 1250
    try:
        collection.parse_money('1.250')
    except ValueError as exc:
        assert 'ambíguo' in str(exc)
    else:
        raise AssertionError('Ambiguous value accepted')
    items = [{'amount': 1000, 'due_date': '2026-10-01', 'paid_date': '2026-11-15'}]
    assert collection.analyze(items, date(2026, 11, 10))['resumo']['valor_aberto'] == 1000
    assert collection.analyze(items, date(2026, 11, 16))['resumo']['valor_aberto'] == 0


def test_redirect_blocked_before_network_access():
    seen = []
    def handler(request):
        seen.append(str(request.url))
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nDisallow: /private')
        return httpx.Response(302, headers={'location': 'http://127.0.0.1/private'})
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    result = discover('https://empresa.com.br/', client=client)
    assert len(seen) == 2 and all('127.0.0.1' not in url for url in seen)
    assert not result['pages_read']
    assert not result['emails']


def test_portfolio_preview_import_and_movements():
    ensure_schema()
    content = 'titulo;valor;vencimento\nNF1;1000;01/10/2026\nNF1;1000;01/10/2026\n'
    with TestClient(app) as c:
        preview = c.post('/api/portfolios/preview', json={'name': 'Regressão', 'csv': content}).json()
        assert preview['possible_duplicates'] == [3]
        assert c.post('/api/portfolios', json={'name': 'Regressão', 'csv': content}).status_code == 409
        r = c.post('/api/portfolios', json={'name': 'Regressão', 'csv': content, 'accept_duplicates': True})
        assert r.status_code == 201
        pid = r.json()['id']; item = r.json()['items'][0]['id']
        again = c.post('/api/portfolios', json={'name': 'Regressão', 'csv': content, 'accept_duplicates': True}).json()
        assert again['reused'] and again['id'] == pid
        movement = {'kind': 'payment', 'amount': 200, 'effective_date': '2026-11-15',
                    'reference': 'comprovante', 'request_id': str(uuid4())}
        mr = c.post(f'/api/portfolios/{pid}/items/{item}/movements', json=movement)
        assert mr.status_code == 201, mr.text
        assert c.post(f'/api/portfolios/{pid}/items/{item}/movements', json=movement).json()['reused']
        assert c.get(f'/api/portfolios/{pid}?reference_date=2026-11-10').json()['resumo']['valor_aberto'] == 2000
        assert c.get(f'/api/portfolios/{pid}?reference_date=2026-11-16').json()['resumo']['valor_aberto'] == 1800
        rid = mr.json()['id']
        reversal = c.post(f'/api/portfolios/{pid}/movements/{rid}/reverse', json={
            'effective_date': '2026-11-17', 'reference': 'estorno', 'request_id': str(uuid4())})
        assert reversal.status_code == 201, reversal.text
        assert c.get(f'/api/portfolios/{pid}?reference_date=2026-11-18').json()['resumo']['valor_aberto'] == 2000
        assert c.delete(f'/api/portfolios/{pid}').status_code == 200
        assert all(x['id'] != pid for x in c.get('/api/portfolios').json())
        assert any(x['id'] == pid for x in c.get('/api/portfolios?archived=true').json())
        assert c.post(f'/api/portfolios/{pid}/restore').status_code == 200


def test_contacts_sync_cursor_and_invalid_status():
    ensure_schema()
    with SessionLocal() as db:
        a = Company(name='Cursor A', institutional_email='contato-a@empresa.com.br')
        b = Company(name='Cursor B', institutional_email='contato-b@empresa.com.br')
        db.add_all([a, b]); db.commit()
        aid, bid = a.id, b.id
    with TestClient(app) as c:
        first = c.post('/api/contacts/sync', params={'limit': 1, 'after_id': aid - 1}).json()
        second = c.post('/api/contacts/sync', params={'limit': 1, 'after_id': first['next_cursor']}).json()
        assert second['scanned'] == 1 and second['next_cursor'] == bid
        rows = c.get('/api/contacts', params={'company_id': bid}).json()['items']
        assert rows
        assert c.patch(f"/api/contacts/{rows[0]['id']}/verify?status=invalido").status_code == 200
        assert c.get(f'/api/companies/{bid}').json()['institutional_email'] is None


def test_owner_login_and_csrf(monkeypatch):
    monkeypatch.setattr(settings, 'admin_password_hash', password_hash('senha-de-teste-muito-forte'))
    monkeypatch.setattr(settings, 'admin_username', 'admin')
    with TestClient(app) as c:
        assert c.get('/api/companies/search').status_code == 401
        login = c.post('/api/auth/login', json={'username': 'admin', 'password': 'senha-de-teste-muito-forte'})
        assert login.status_code == 200, login.text
        assert c.get('/api/companies/search').status_code == 200
        assert c.post('/api/contacts/sync').status_code == 403
        csrf = login.json()['csrf_token']
        assert c.post('/api/contacts/sync', headers={'X-CSRF-Token': csrf}).status_code == 200
        assert c.post('/api/auth/logout', headers={'X-CSRF-Token': csrf}).status_code == 200
        assert c.get('/api/companies/search').status_code == 401


def test_production_configuration_and_secure_session(monkeypatch):
    import pytest
    ensure_schema()
    monkeypatch.setattr(settings, 'app_env', 'production')
    monkeypatch.setattr(settings, 'admin_username', 'owner')
    monkeypatch.setattr(settings, 'admin_password_hash', password_hash('senha-de-teste-muito-forte'))
    monkeypatch.setattr(settings, 'public_url', 'https://painel.example.com')
    monkeypatch.setattr(settings, 'db_host', '')
    monkeypatch.setattr(settings, 'postgres_password', '')
    with pytest.raises(RuntimeError, match='PostgreSQL'):
        validate_configuration()
    monkeypatch.setattr(settings, 'db_host', 'db')
    monkeypatch.setattr(settings, 'postgres_password', 'senha-de-banco')
    validate_configuration()
    # ASGI TestClient uses the test SQLite database; this exercises HTTPS cookie,
    # origin and CSRF middleware separately from the unavailable Docker stack.
    import importlib
    monkeypatch.setattr(importlib.import_module('app.main'), 'check_schema_revision', lambda: None)
    with TestClient(app, base_url='https://painel.example.com') as c:
        assert c.get('/api/health').status_code == 200
        assert c.get('/api/companies/search').status_code == 401
        login = c.post('/api/auth/login', json={'username': 'owner', 'password': 'senha-de-teste-muito-forte'})
        assert login.status_code == 200
        assert 'Secure' in login.headers['set-cookie']
        csrf = login.json()['csrf_token']
        assert c.get('/api/companies/search').status_code == 200
        assert c.post('/api/contacts/sync', headers={'X-CSRF-Token': csrf,
               'Origin': 'https://outro.example.com'}).status_code == 403
        assert c.post('/api/contacts/sync', headers={'X-CSRF-Token': csrf,
               'Origin': 'https://painel.example.com'}).status_code == 200


def test_assistant_approval_uses_real_task(monkeypatch):
    import openai
    ensure_schema()
    with SessionLocal() as db:
        company = Company(name='Empresa assistida')
        db.add(company); db.commit(); cid = company.id
    monkeypatch.setattr(settings, 'openai_api_key', 'stubbed')
    monkeypatch.setattr(settings, 'openai_model', 'test-model')
    monkeypatch.setattr(settings, 'assistant_monthly_budget_usd', 100)
    monkeypatch.setattr(settings, 'openai_input_usd_per_million', 1)
    monkeypatch.setattr(settings, 'openai_output_usd_per_million', 1)
    class Usage:
        input_tokens = 100
        output_tokens = 20
    class Call:
        type = 'function_call'
        name = 'prepare_task'
        call_id = 'call_1'
        arguments = '{"company_id": %d, "title": "Retornar ligação", "due_at": null}' % cid
        def model_dump(self, **kw):
            return {'type': 'function_call', 'call_id': self.call_id,
                    'name': self.name, 'arguments': self.arguments}
    class Response:
        def __init__(self, first):
            self.usage = Usage()
            self.output = [Call()] if first else []
            self.output_text = 'Tarefa pronta para confirmar.'
    class FakeClient:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def __init_subclass__(cls): pass
        calls = 0
        class responses:
            @staticmethod
            def create(**kw):
                FakeClient.calls += 1
                return Response(first=FakeClient.calls == 1)
    monkeypatch.setattr(openai, 'OpenAI', FakeClient)
    with TestClient(app) as c:
        response = c.post('/api/assistant/messages', json={'request_id': str(uuid4()),
                          'message': 'Crie tarefa para retornar a ligação'}).json()
        assert response['actions'] and response['actions'][0]['status'] == 'pending'
        action_id = response['actions'][0]['id']
        assert c.post(f'/api/assistant/actions/{action_id}/confirm').status_code == 200
        assert c.post(f'/api/assistant/actions/{action_id}/confirm').json()['reused']
        with SessionLocal() as db:
            assert db.query(Task).filter_by(company_id=cid, title='Retornar ligação').count() == 1
