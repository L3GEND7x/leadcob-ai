import pytest
from app.core.config import settings
from app.core.security import validate_configuration, password_hash


def test_commercial_production_startup_is_fail_closed(monkeypatch):
    configuration={
        "app_env":"production",
        "admin_password_hash":password_hash("synthetic-test-password-long"),
        "public_url":"https://leadcob.example.test",
        "database_url":"postgresql://app:password@example.test:5432/db",
        "db_host":"",
        "postgres_password":"",
        "demo_seed":False,
        "commercial_auth_enabled":False,
        "commercial_entitlements_enabled":False,
        "workspace_assistant_enabled":False,
        "workspace_registry_search_enabled":False,
        "workspace_assistant_monthly_budget_usd":0.0,
        "openai_api_key":"",
        "openai_model":"",
        "openai_input_usd_per_million":0.0,
        "openai_output_usd_per_million":0.0,
    }
    for key,value in configuration.items():
        monkeypatch.setattr(settings,key,value)
    validate_configuration()  # existing owner-only service remains valid
    monkeypatch.setattr(settings,"commercial_auth_enabled",True)
    with pytest.raises(RuntimeError,match="limites de assinatura"):
        validate_configuration()
    monkeypatch.setattr(settings,"commercial_auth_enabled",False)
    monkeypatch.setattr(settings,"workspace_registry_search_enabled",True)
    with pytest.raises(RuntimeError,match="Recursos experimentais"):
        validate_configuration()
    monkeypatch.setattr(settings,"workspace_registry_search_enabled",False)
    monkeypatch.setattr(settings,"commercial_auth_enabled",True)
    monkeypatch.setattr(settings,"commercial_entitlements_enabled",True)
    validate_configuration()  # pilot portal with explicit subscription enforcement
    monkeypatch.setattr(settings,"workspace_assistant_enabled",True)
    with pytest.raises(RuntimeError,match="IA comercial"):
        validate_configuration()
    for key,value in dict(workspace_assistant_monthly_budget_usd=1.0,openai_api_key="fixture",
        openai_model="fixture",openai_input_usd_per_million=1.0,
        openai_output_usd_per_million=2.0).items():
        monkeypatch.setattr(settings,key,value)
    validate_configuration()  # syntax/config only; not proof of a paid API call
