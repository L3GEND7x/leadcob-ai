"""Release preflight inside the private production environment.

Only aggregate diagnostics, read-only PostgreSQL transaction, no provider generation.
Use as an explicit pre-deploy command after migrations; not a public route.
"""
import json
import os
import re
import time

from sqlalchemy import text
from app.core.config import settings
from app.db.database import SessionLocal, check_schema_revision
from app.api.routes_crm import command_center, search_companies, pipeline
from app.api.routes_assistant import assistant_status
from app.jobs.final_owner_acceptance import finance_ok, SCENARIO
from app.jobs.owner_acceptance import verify
from app.services.registry_coverage import registry_coverage
from app.services.lead_qualification import qualification
from app.services.contact_readiness import contactability
from app.services.commercial_readiness import readiness
from app.services.negotiation import simulate


def audit(db):
    revision=os.getenv("RAILWAY_GIT_COMMIT_SHA","")
    report={"revision":revision if re.fullmatch("[0-9a-f]{40}",revision) else None,
            "scope":{"uf":"AM","city":"Manaus"},"checks":[],
            "provider_generation_tested":False,"authenticated_http_tested":False,
            "national_coverage_certified":False,"production_release_ready":False}
    checks=(
        ("registry",lambda:registry_coverage(db,"AM","Manaus")),
        ("qualification",lambda:qualification(db,"AM","Manaus",limit=1)),
        ("contactability",lambda:contactability(db,"AM","Manaus")),
        ("command_center",lambda:command_center(db=db)),
        ("company_search",lambda:search_companies(uf="AM",municipio="Manaus",sort="name",page=1,per_page=1,db=db)),
        ("pipeline",lambda:pipeline(db=db)),
        ("assistant",lambda:assistant_status(db=db)),
        ("commercial_readiness",lambda:readiness(db,settings)),
    )
    for name,fn in checks:
        started=time.monotonic()
        try:
            ok,metrics=verify(name,fn())
        except Exception:
            # Exceptions can contain SQL, business records or credentials; emit no details.
            report["checks"].append({"check":name,"passed":False,"reason":"internal_check_failed"})
            break
        report["checks"].append({"check":name,"passed":bool(ok),"metrics":metrics,
                                 "seconds":round(time.monotonic()-started,3)})
    report["checks"].append({"check":"finance_synthetic","passed":finance_ok(simulate(SCENARIO))})
    report["checks_passed"]=len(report["checks"])==len(checks)+1 and all(c["passed"] for c in report["checks"])
    return report


def main():
    if settings.app_env.strip().lower()!="production":
        raise SystemExit("Use somente no ambiente privado de produção autorizado.")
    try:
        check_schema_revision()
        with SessionLocal() as db:
            if db.get_bind().dialect.name!="postgresql":
                raise ValueError("PostgreSQL required.")
            db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            db.execute(text("SET LOCAL statement_timeout = '45s'"))
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            report=audit(db)
            db.rollback()
    except Exception:
        print(json.dumps({"checks_passed":False,"reason":"preflight_failed",
                          "production_release_ready":False}),flush=True)
        raise SystemExit(1) from None
    print(json.dumps(report,ensure_ascii=False,sort_keys=True),flush=True)
    # A failed external configuration check must not be interpreted as a passed release.
    if not report["checks_passed"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
