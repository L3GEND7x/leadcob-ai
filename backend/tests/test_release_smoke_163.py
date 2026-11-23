import pytest
from app.jobs.release_smoke import CHECKS, ReleaseSmokeFailed, run, validate_base
from app.db.database import Base
from app.db import models
from alembic.config import Config
from alembic.script import ScriptDirectory
from pathlib import Path


SHA="a"*40


def fake_response(enabled=False, revision=SHA):
    statuses={"health":200,"dashboard":200,"styles":200,"commercial_asset":200,
        "commercial_page":200 if enabled else 404,
        "commercial_session":200 if enabled else 404,
        "owner_admin_private":401,"owner_discovery_private":401,"owner_readiness_private":401}
    def transport(base,method,path):
        name=next(name for name,m,p in CHECKS if p==path)
        assert method=="GET"
        assert base=="https://example.test"
        body=b""
        if name=="health":
            body=('{"status":"ok","revision":"'+revision+'"}').encode()
        if name=="commercial_session" and enabled:
            body=b'{"authenticated":false}'
        return statuses[name],body
    return transport


def test_release_anonymous_smoke_disabled_and_enabled():
    for enabled in (False,True):
        result=run("https://example.test/",commercial_enabled=enabled,
            expected_sha=SHA,request=fake_response(enabled))
        assert result["checks_passed"]
        assert len(result["checks"])==len(CHECKS)
        assert result["production_release_ready"] is False
        assert all(x["passed"] for x in result["checks"])


def test_release_smoke_rejects_stale_build_private_leak_and_bad_url():
    result=run("https://example.test",expected_sha=SHA,request=fake_response(revision="b"*40))
    assert not result["checks_passed"]
    assert result["failures"]==["health"]
    def leaky(base,method,path):
        status,body=fake_response()(base,method,path)
        if path=="/owner/commercial":
            return 200,b"private owner page"
        return status,body
    assert "owner_admin_private" in run("https://example.test",request=leaky)["failures"]
    for url in ("http://example.test","https://user:pass@example.test",
                "file:///etc/passwd","https://example.test/path","https://example.test/?x=1"):
        with pytest.raises(ReleaseSmokeFailed):
            validate_base(url)
    with pytest.raises(ReleaseSmokeFailed):
        run("https://example.test",expected_sha="invalid",request=fake_response())


def test_release_migration_chain_has_single_current_head_and_required_tables():
    root=Path(__file__).resolve().parents[2]
    script=ScriptDirectory.from_config(Config(str(root/"alembic.ini")))
    assert script.get_heads()==["d161a20261123"]
    for name in ("commercial_renewals","workspace_assistant_exchanges",
                 "workspace_registry_query_quotas","workspace_prospect_imports",
                 "contact_worker_heartbeats","commercial_invoices",
                 "asaas_sandbox_issue_reservations"):
        assert name in Base.metadata.tables
