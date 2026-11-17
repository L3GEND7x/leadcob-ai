from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.core.config import Settings
from app.services.commercial_readiness import readiness


def test_readiness_reports_incomplete_configuration_without_secrets():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    config = Settings(_env_file=None, app_env="development", public_url="http://localhost",
                      commercial_auth_enabled=False, commercial_entitlements_enabled=False,
                      admin_password_hash="test-secret-hash", asaas_sandbox_api_key="test-secret-key",
                      asaas_sandbox_webhook_token="x"*32, demo_seed=False)
    with Session(engine) as db:
        result = readiness(db, config)
    assert result["configuration_checks"]["schema_tables_present"] is True
    assert result["configuration_checks"]["postgresql"] is False
    assert result["configuration_checks_passed"] is False
    assert result["release_ready"] is False
    assert "test-secret" not in str(result)
    engine.dispose()
