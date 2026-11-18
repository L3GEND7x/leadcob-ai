"""CI-only logical backup/restore drill. Never uses the configured application database.

Creates two randomly named disposable databases on a dedicated local PostgreSQL
test instance. Dumps only synthetic data, restores into the second database,
checks rows and financial totals, then removes both databases and the dump.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import re
import tempfile
import time
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, select, func, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import (
    Organization, CommercialPlan, CommercialSubscription, CommercialInvoice,
    WorkspacePortfolio, WorkspacePortfolioTitle, WorkspaceLead,
    AsaasSandboxCustomer, AsaasSandboxIssueReservation,
)


def run(raw_url):
    url=make_url(raw_url)
    if (url.get_backend_name()!="postgresql" or url.host not in {"localhost","127.0.0.1"}
            or url.database!="leadcob_test" or url.username!="leadcob_test" or url.query):
        raise ValueError("Dedicated local leadcob_test PostgreSQL instance required.")
    suffix=uuid4().hex
    source="drill_src_"+suffix
    target="drill_dst_"+suffix
    admin=create_engine(url,isolation_level="AUTOCOMMIT")
    created=[]
    engines=[]
    # No password in command-line arguments, output or report.
    env={k:v for k,v in os.environ.items() if not k.startswith("PG")}
    env.update(PGHOST=url.host,PGPORT=str(url.port or 5432),PGUSER=url.username,
               PGPASSWORD=url.password or "",PGCONNECT_TIMEOUT="5")
    def cmd(args):
        try:
            subprocess.run(args,env=env,check=True,timeout=120,
                           stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as exc:
            # This drill accepts only synthetic records; never emit the command or credentials.
            raise RuntimeError(f"{args[0]} failed (exit {exc.returncode}): "
                + (exc.stderr or b"").decode(errors="replace")[:1000]) from None
    try:
        with admin.connect() as conn:
            major = int(conn.exec_driver_sql("SHOW server_version_num").scalar_one()) // 10000
            for tool in ("pg_dump", "pg_restore"):
                version = subprocess.check_output([tool, "--version"], env=env, text=True, timeout=30)
                match = re.search(r"PostgreSQL\)\s+(\d+)", version)
                if not match or int(match.group(1)) != major:
                    raise RuntimeError("Backup client major must match the PostgreSQL server.")
            for name in (source,target):
                conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
                created.append(name)
        src=create_engine(url.set(database=source))
        dst=create_engine(url.set(database=target))
        engines.extend([src,dst])
        Base.metadata.create_all(src)
        now=datetime.now(timezone.utc)
        with Session(src) as db:
            a=Organization(name="Synthetic A",slug="synthetic-a",active=True)
            b=Organization(name="Synthetic B",slug="synthetic-b",active=True)
            plan=CommercialPlan(code="fixture",name="Fixture",monthly_price_cents=2700,
                max_members=1,max_leads=10,max_contacts=10,max_tasks=10,max_portfolios=10,max_titles=10,active=True)
            db.add_all([a,b,plan]);db.flush()
            db.add(CommercialSubscription(organization_id=a.id,plan_id=plan.id,
                starts_at=now,ends_at=now+timedelta(days=30),status="active"))
            invoice=CommercialInvoice(organization_id=a.id,plan_id=plan.id,
                period_start="2026-11-01",period_end="2026-12-01",due_date="2026-11-01",amount_cents=2700)
            portfolio=WorkspacePortfolio(organization_id=a.id,name="Fixture portfolio",reference_date="2026-11-01")
            db.add_all([invoice,portfolio,WorkspaceLead(organization_id=a.id,name="Synthetic lead",notes="",stage="identified")])
            db.flush()
            db.add_all([
                WorkspacePortfolioTitle(portfolio_id=portfolio.id,reference="A",amount=Decimal("123.45"),due_date="2026-11-01"),
                WorkspacePortfolioTitle(portfolio_id=portfolio.id,reference="B",amount=Decimal("876.55"),due_date="2026-11-02"),
                AsaasSandboxCustomer(organization_id=a.id,customer_id="cus_fixture"),
                AsaasSandboxIssueReservation(invoice_id=invoice.id,customer_id="cus_fixture",
                    external_reference="fixture",billing_type="PIX",amount_cents=2700,due_date="2026-11-01",created_at=now),
            ])
            db.commit()
        def snapshot(engine):
            with Session(engine) as db:
                counts={t.name:db.scalar(select(func.count()).select_from(t)) for t in Base.metadata.sorted_tables}
                totals={
                    "invoice_cents":db.scalar(select(func.sum(CommercialInvoice.amount_cents))),
                    "portfolio_brl":str(db.scalar(select(func.sum(WorkspacePortfolioTitle.amount)))),
                    "sandbox_reserved_cents":db.scalar(select(func.sum(AsaasSandboxIssueReservation.amount_cents))),
                }
                return {"counts":counts,"totals":totals,
                    "tables":sorted(inspect(engine).get_table_names())}
        before=snapshot(src)
        assert before["totals"]=={"invoice_cents":2700,"portfolio_brl":"1000.00","sandbox_reserved_cents":2700}
        with tempfile.TemporaryDirectory(prefix="leadcob-restore-") as folder:
            dump=Path(folder)/"synthetic.dump"
            start=time.perf_counter()
            cmd(["pg_dump","--format=custom","--no-owner","--no-acl","--file",str(dump),"--dbname",source])
            backup_seconds=time.perf_counter()-start
            digest=hashlib.sha256(dump.read_bytes()).hexdigest()
            size=dump.stat().st_size
            start=time.perf_counter()
            cmd(["pg_restore","--exit-on-error","--single-transaction","--no-owner","--no-acl",
                 "--dbname",target,str(dump)])
            restore_seconds=time.perf_counter()-start
            after=snapshot(dst)
            assert before==after,"Restored counts, tables or financial totals differ."
            with Session(dst) as db:
                # Check distinct tenant ownership and sequence continuity.
                a=db.scalar(select(Organization).where(Organization.slug=="synthetic-a"))
                b=db.scalar(select(Organization).where(Organization.slug=="synthetic-b"))
                assert a.id!=b.id
                assert db.scalar(select(func.count()).select_from(WorkspaceLead).where(WorkspaceLead.organization_id==b.id))==0
                assert db.scalar(select(func.count()).select_from(WorkspaceLead).where(WorkspaceLead.organization_id==a.id))==1
                extra=Organization(name="Sequence check",slug="sequence-check")
                db.add(extra);db.flush()
                assert extra.id>max(a.id,b.id)
                db.rollback()
            return {"synthetic":True,"restored":True,"tables_checked":len(before["tables"]),
                    "row_counts_match":True,"financial_totals_match":True,
                    "tenant_ownership_checked":True,"sequence_checked":True,
                    "backup_bytes":size,"sha256":digest,"backup_seconds":backup_seconds,
                    "restore_seconds":restore_seconds,"production_ready":False}
    finally:
        for engine in engines:
            engine.dispose()
        try:
            with admin.connect() as conn:
                for name in reversed(created):
                    conn.exec_driver_sql(f'DROP DATABASE "{name}"')
        finally:
            admin.dispose()


if __name__=="__main__":
    print(json.dumps(run(os.environ["LEADCOB_TEST_POSTGRES_URL"]),indent=2))
