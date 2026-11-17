"""Seed the dedicated disposable SQLite database only."""
import os
from datetime import datetime, timedelta, timezone
from app.db.database import ensure_schema, SessionLocal, engine
from app.db.models import Organization, AccountUser, Membership, CommercialPlan, CommercialSubscription
from app.core.security import password_hash

if engine.url.get_backend_name() != "sqlite" or engine.url.database != "/tmp/leadcob-browser-133.db":
    raise RuntimeError("Refusing to seed any non-browser-test database")
ensure_schema()
with SessionLocal() as db:
    org=Organization(id=1,name="Browser E2E",slug="browser-e2e",active=True)
    user=AccountUser(email="browser@example.test",password_hash=password_hash("browser-test-password"),active=True)
    plan=CommercialPlan(code="essential-e2e",name="Essential",monthly_price_cents=2700,
        max_members=2,max_leads=100,max_contacts=100,max_tasks=100,max_portfolios=10,max_titles=100,active=True)
    db.add_all([org,user,plan]);db.flush()
    now=datetime.now(timezone.utc)
    db.add(Membership(user_id=user.id,organization_id=org.id,role="admin",active=True))
    db.add(CommercialSubscription(organization_id=org.id,plan_id=plan.id,starts_at=now-timedelta(days=1),ends_at=now+timedelta(days=30),status="active"))
    db.commit()
