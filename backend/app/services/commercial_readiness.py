"""Configuration and schema diagnostics, not a certification of production readiness."""
from sqlalchemy import inspect, select, func
from app.db.models import CommercialPlan, Organization
from app.db.database import Base


def readiness(db, settings):
    from urllib.parse import urlparse
    parsed = urlparse(settings.public_url)
    bind = db.get_bind()
    present = set(inspect(db.connection()).get_table_names())
    missing = sorted(set(Base.metadata.tables) - present)
    checks = {
        "production_mode": settings.app_env == "production",
        "postgresql": bind.dialect.name == "postgresql",
        "https_origin": parsed.scheme == "https" and bool(parsed.hostname)
            and not parsed.username and not parsed.password and parsed.path in ("", "/")
            and not parsed.query and not parsed.fragment,
        "owner_auth_configured": bool(settings.admin_password_hash),
        "commercial_auth_enabled": settings.commercial_auth_enabled,
        "entitlements_enabled": settings.commercial_entitlements_enabled,
        "demo_disabled": not settings.demo_seed,
        "schema_tables_present": not missing,
    }
    plans = []
    if "commercial_plans" in present:
        plans = [dict(code=p.code, amount_cents=p.monthly_price_cents, active=p.active)
                 for p in db.scalars(select(CommercialPlan).order_by(CommercialPlan.id))]
    expected = {"essential":2700,"professional":11700,"enterprise":39700}
    checks["expected_active_catalog"] = all(any(p["active"] and p["amount_cents"] == price
        and (p["code"] == code or p["code"].startswith(code+"-")) for p in plans)
        for code,price in expected.items())
    return {
        "configuration_checks": checks,
        "configuration_checks_passed": all(checks.values()),
        "missing_tables": missing,
        "plans": plans,
        "sandbox": {"api_configured": bool(settings.asaas_sandbox_api_key),
                    "webhook_token_configured": len(settings.asaas_sandbox_webhook_token) >= 32},
        "release_ready": False,
        "manual_gates": ["postgresql_concurrency", "browser_e2e", "sandbox_provider_homologation",
                         "backup_restore_drill", "privacy_and_terms_review", "production_payment_integration"],
    }
