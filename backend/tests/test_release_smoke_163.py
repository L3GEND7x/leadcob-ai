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
        "owner_admin_private":401,"owner_discovery_private":401,"owner_readiness_private":401,
        "owner_contact_export_private":401,"owner_contactability_private":401,
        "owner_registry_coverage_private":401,
        "owner_registry_qualification_private":401,
        "owner_contact_coverage_private":401,
        "owner_discovery_targets_private":401,
        "owner_worker_diagnostics_private":401,
        "owner_discovery_jobs_private":401}
    statuses.update({name:401 for name,_,_ in CHECKS if name.endswith("_private")})
    statuses["owner_session_anonymous"]=200
    def transport(base,method,path):
        name=next(name for name,m,p in CHECKS if p==path)
        assert method=="GET"
        assert base=="https://example.test"
        body=b""
        if name=="health":
            body=('{"status":"ok","revision":"'+revision+'"}').encode()
        if name=="owner_session_anonymous":
            body=b'{"authenticated":false,"username":null,"csrf_token":"","mode":"cloud"}'
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
    for endpoint,check in (("/api/contacts/export.csv?uf=AM&city=Manaus","owner_contact_export_private"),
                           ("/api/contacts/contactability?uf=AM&city=Manaus","owner_contactability_private")):
        def leak_contact(base,method,path):
            return (200,b"private") if path==endpoint else fake_response()(base,method,path)
        assert check in run("https://example.test",request=leak_contact)["failures"]
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


@pytest.mark.parametrize("check,path", [
    ("owner_registry_coverage_private", "/api/registry/coverage?uf=AM&city=Manaus"),
    ("owner_registry_qualification_private", "/api/registry/qualification?uf=AM&city=Manaus"),
    ("owner_contact_coverage_private", "/api/contacts/coverage?uf=AM&city=Manaus"),
    ("owner_discovery_targets_private", "/api/contacts/discovery-targets?uf=AM&city=Manaus&kind=email"),
    ("owner_worker_diagnostics_private", "/api/contacts/worker-diagnostics"),
    ("owner_discovery_jobs_private", "/api/contacts/discovery-jobs?limit=1&offset=0"),
])
def test_private_prospecting_routes_fail_smoke_on_anonymous_success(check, path):
    def leaky(base, method, target):
        if target == path:
            return 200, b"private"
        return fake_response()(base, method, target)
    result = run("https://example.test", request=leaky)
    assert not result["checks_passed"]
    assert check in result["failures"]

@pytest.mark.parametrize("check,path", [
    (name,path) for name,_,path in CHECKS if name.endswith("_private")
])
def test_every_private_surface_rejects_anonymous_200(check,path):
    def transport(base,method,target):
        if target==path:
            return 200,b"do not expose this body"
        return fake_response()(base,method,target)
    result=run("https://example.test",request=transport)
    assert check in result["failures"]
    assert "do not expose this body" not in str(result)


@pytest.mark.parametrize("body", [
    b'{"authenticated":true,"mode":"local"}',
    b'{"authenticated":false,"mode":"cloud","csrf_token":"leaked"}',
    b'{"authenticated":false,"mode":"cloud","username":"owner"}',
    b'{"authenticated":false}',
    b'not json',
])
def test_owner_session_must_be_anonymous_and_cloud(body):
    def transport(base,method,path):
        if path=="/api/auth/session":
            return 200,body
        return fake_response()(base,method,path)
    result=run("https://example.test",request=transport)
    assert "owner_session_anonymous" in result["failures"]
    assert "leaked" not in str(result)
