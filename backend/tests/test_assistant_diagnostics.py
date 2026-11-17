from app.api.routes_assistant import configuration_checks, configured, failure_category, failure_metadata
from app.core.config import settings


def test_configuration_requires_finite_positive_prices(monkeypatch):
    for key,value in dict(openai_api_key="test-secret",openai_model="test-model",
        assistant_monthly_budget_usd=10,openai_input_usd_per_million=1,
        openai_output_usd_per_million=2).items():
        monkeypatch.setattr(settings,key,value)
    assert configured()
    assert "test-secret" not in str(configuration_checks())
    for value in (float("inf"),float("nan"),0,-1):
        monkeypatch.setattr(settings,"openai_input_usd_per_million",value)
        assert not configured()
    monkeypatch.setattr(settings,"openai_api_key"," ")
    assert not configuration_checks()["api_key"]


def test_provider_error_categories_do_not_expose_body():
    class ProviderError(Exception):
        status_code=429
        body={"code":"insufficient_quota","message":"secret provider body"}
    meta=failure_metadata(ProviderError())
    assert failure_category(meta)=="provider_quota"
    assert "secret" not in str(meta)
    assert failure_category({"status":401})=="provider_auth"
    assert failure_category({"status":404})=="provider_model"
    assert failure_category({"status":429})=="provider_rate_limit"
    assert failure_category({"type":"APITimeoutError"})=="provider_connection"
