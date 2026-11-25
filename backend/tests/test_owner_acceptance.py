import httpx
from app.jobs import owner_acceptance as job

BASE="https://example.test"
SHA="a"*40

REG=dict(company_records=6,missing_cnpj_records=1,invalid_cnpj_records=1,
         valid_cnpj_records=4,unique_valid_cnpjs=3,duplicate_valid_records=1,
         active_cnpjs=2,inactive_cnpjs=1,unknown_status_cnpjs=0,conflicting_status_cnpjs=0)
CONTACT=dict(valid_unique_cnpjs=3,active_unique_cnpjs=2,active_corporate_cnpjs=2,
             with_any_direct_channel=1,with_verified_direct_channel=1,
             with_verified_sourced_direct_channel=0,without_direct_channel=1)
ASSIST=dict(configured=True,configuration_checks=dict.fromkeys(
    ("api_key","model","monthly_budget","input_price","output_price"),True))
CORE=dict(configuration_checks=dict.fromkeys(
    ("production_mode","postgresql","https_origin","owner_auth_configured","demo_disabled","schema_tables_present"),True))


def test_aggregate_validation():
    for name,data in (("registry",REG),("contactability",CONTACT),("assistant",ASSIST),("commercial_readiness",CORE)):
        assert job.verify(name,data)[0]
    assert not job.verify("registry",dict(REG,unique_valid_cnpjs=999))[0]
    assert not job.verify("contactability",dict(CONTACT,with_verified_direct_channel=3))[0]
    assert not job.verify("assistant",dict(ASSIST,configured=False))[0]
    assert not job.verify("commercial_readiness",{})[0]


def test_owner_acceptance_real_http_contract_with_mock_transport():
    calls=[]
    session=False
    payloads={"command_center":{"kpis":{"empresas_total":1,"leads_qualificados":0}},
        "daily_intelligence":{},"company_search":{"items":[]},"registry":REG,
        "qualification":{"unique_cnpjs":3,"total":3,"counts":{"prospect_research":3},"items":[]},
        "contactability":CONTACT,"pipeline":{"stages":[]},"assistant":ASSIST,"commercial_readiness":CORE}
    def handler(req):
        nonlocal session
        path=req.url.path
        calls.append((req.method,path))
        if path=="/api/health":
            return httpx.Response(200,json={"status":"ok","revision":SHA})
        if path=="/api/auth/login":
            session=True
            return httpx.Response(200,json={"authenticated":True,"csrf_token":"test-token"},
                                  headers={"Set-Cookie":"leadcob_session=private; Secure; HttpOnly; Path=/"})
        if path=="/api/auth/session":
            return httpx.Response(200,json={"authenticated":session})
        if path=="/api/auth/logout":
            assert req.headers["X-CSRF-Token"]=="test-token"
            session=False
            return httpx.Response(200,json={"ok":True})
        assert req.method=="GET" and session and req.headers["Cookie"]=="leadcob_session=private"
        name=next(n for n,p in job.CHECKS if p.split("?")[0]==path)
        return httpx.Response(200,json=payloads[name])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report=job.run(client,BASE,"owner","test-password",SHA)
    assert report["checks_passed"] and report["session_revoked"]
    assert report["owner_release_ready"] is False and report["provider_verified"] is False
    assert "test-password" not in str(report) and "test-token" not in str(report)
    assert [path for method,path in calls if method=="POST"]==["/api/auth/login","/api/auth/logout"]


def test_stale_revision_never_sends_credentials():
    def handler(req):
        assert req.method=="GET" and req.url.path=="/api/health"
        return httpx.Response(200,json={"status":"ok","revision":"b"*40})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report=job.run(client,BASE,"owner","test-password",SHA)
    assert not report["checks_passed"]
    assert report["checks"]==[{"check":"deployed_revision","passed":False,"status":200}]
