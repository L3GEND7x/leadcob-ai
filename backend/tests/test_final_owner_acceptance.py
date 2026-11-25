import httpx
from app.jobs import final_owner_acceptance as job
from app.services.negotiation import simulate

SHA="a"*40
BASE="https://example.test"


def test_financial_fixture():
    valid=simulate(job.SCENARIO)
    assert job.finance_ok(valid)
    assert not job.finance_ok(dict(valid,total_a_receber=1031))
    assert not job.finance_ok({})


def test_ai_is_opt_in_and_secrets_never_reported():
    for ai in (False,True):
        calls=[]
        authenticated=False
        def handler(req):
            nonlocal authenticated
            path=req.url.path
            calls.append(path)
            if path=="/api/health":
                return httpx.Response(200,json={"revision":SHA})
            if path=="/api/auth/login":
                authenticated=True
                return httpx.Response(200,json={"authenticated":True,"csrf_token":"secret-csrf"})
            if path=="/api/auth/logout":
                authenticated=False
                return httpx.Response(200,json={"ok":True})
            if path=="/api/auth/session":
                return httpx.Response(200,json={"authenticated":authenticated})
            assert authenticated
            if path=="/api/negotiation/simulate":
                return httpx.Response(200,json=simulate(job.SCENARIO))
            if path=="/api/assistant/provider-check":
                return httpx.Response(200,json={"model_accessible":True})
            if path=="/api/assistant/generation-check":
                return httpx.Response(200,json={"generation_passed":True})
            assert req.method=="GET"
            return httpx.Response(200,json=[])
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result=job.additional(client,BASE,"owner","secret-password",SHA,ai=ai)
        assert result["checks_passed"] and result["session_revoked"]
        assert result["provider_generation_tested"] is ai
        assert ("/api/assistant/generation-check" in calls) is ai
        assert "secret-" not in str(result)
        assert result["full_release_certified"] is False
