"""Conservative remote smoke checks. Does not authenticate, modify data or invoke paid services."""
import argparse
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request


class ReleaseSmokeFailed(RuntimeError):
    pass


CHECKS = (
    ("health", "GET", "/api/health"),
    ("dashboard", "GET", "/"),
    ("styles", "GET", "/static/styles.css"),
    ("commercial_asset", "GET", "/static/commercial.js"),
    ("commercial_page", "GET", "/commercial"),
    ("commercial_session", "GET", "/api/commercial/auth/session?organization_id=1"),
    ("owner_session_anonymous", "GET", "/api/auth/session"),
    ("owner_dashboard_private", "GET", "/api/dashboard/summary"),
    ("owner_command_center_private", "GET", "/api/command-center"),
    ("owner_daily_intelligence_private", "GET", "/api/daily-intelligence?limit=1"),
    ("owner_company_search_private", "GET", "/api/companies/search?uf=AM&page=1&per_page=1"),
    ("owner_company_export_private", "GET", "/api/export/companies.csv"),
    ("owner_pipeline_private", "GET", "/api/pipeline"),
    ("owner_tasks_private", "GET", "/api/tasks"),
    ("owner_portfolios_private", "GET", "/api/portfolios"),
    ("owner_reports_private", "GET", "/api/reports/summary"),
    ("owner_assistant_status_private", "GET", "/api/assistant/status"),
    ("owner_assistant_history_private", "GET", "/api/assistant/conversations"),
    ("owner_admin_private", "GET", "/owner/commercial"),
    ("owner_discovery_private", "GET", "/owner/discovery"),
    ("owner_readiness_private", "GET", "/api/owner/commercial/readiness"),
    ("owner_contact_export_private", "GET", "/api/contacts/export.csv?uf=AM&city=Manaus"),
    ("owner_contactability_private", "GET", "/api/contacts/contactability?uf=AM&city=Manaus"),
    ("owner_registry_coverage_private", "GET", "/api/registry/coverage?uf=AM&city=Manaus"),
    ("owner_registry_qualification_private", "GET", "/api/registry/qualification?uf=AM&city=Manaus"),
    ("owner_contact_coverage_private", "GET", "/api/contacts/coverage?uf=AM&city=Manaus"),
    ("owner_discovery_targets_private", "GET", "/api/contacts/discovery-targets?uf=AM&city=Manaus&kind=email"),
    ("owner_worker_diagnostics_private", "GET", "/api/contacts/worker-diagnostics"),
    ("owner_discovery_jobs_private", "GET", "/api/contacts/discovery-jobs?limit=1&offset=0"),
)


def transport(base, method, path, timeout=8):
    """No cookies, no credentials, no redirects and no mutating methods."""
    if method != "GET":
        raise ReleaseSmokeFailed("Only GET is permitted in the remote smoke harness.")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    req = urllib.request.Request(base + path, headers={"Accept":"application/json, text/html, */*",
        "User-Agent":"LeadCob-Release-Smoke/1.0"}, method="GET")
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(req, timeout=timeout) as response:
            status = response.status
            body = response.read(8192) if path in ("/api/health", "/api/auth/session") or "commercial/auth/session" in path else b""
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = b""
    return status, body


def validate_base(base):
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        raise ReleaseSmokeFailed("Invalid URL.")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ReleaseSmokeFailed("Remote smoke requires HTTPS.")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ReleaseSmokeFailed("Use a plain base URL without path, query or fragment.")
    return base.rstrip("/")


def run(base_url, *, commercial_enabled=False, expected_sha=None, request=None):
    base=validate_base(base_url)
    if expected_sha is not None and (len(expected_sha)!=40 or any(
            ch not in "0123456789abcdef" for ch in expected_sha.lower())):
        raise ReleaseSmokeFailed("Invalid expected commit SHA.")
    request=request or transport
    result=[]
    failures=[]
    for name,method,path in CHECKS:
        try:
            status,body=request(base,method,path)
            if name in ("health","dashboard","styles","commercial_asset"):
                ok=status==200
            elif name=="owner_session_anonymous":
                ok=status==200
            elif name=="commercial_page":
                ok=status==(200 if commercial_enabled else 404)
            elif name=="commercial_session":
                ok=status==(200 if commercial_enabled else 404)
            else:
                ok=status in (401,403)
            if name=="health" and status==200:
                try:
                    health=json.loads(body)
                    ok=ok and health.get("status")=="ok"
                    if expected_sha:
                        ok=ok and health.get("revision","").lower()==expected_sha.lower()
                except (ValueError,AttributeError,TypeError):
                    ok=False
            if name in ("commercial_session","owner_session_anonymous") and status==200:
                try:
                    session=json.loads(body)
                    ok=ok and session.get("authenticated") is False
                    if name=="owner_session_anonymous":
                        ok=ok and session.get("mode")=="cloud" and not session.get("csrf_token") and not session.get("username")
                except (ValueError,AttributeError,TypeError):
                    ok=False
        except Exception:
            status=None
            ok=False
        result.append(dict(check=name,status=status,passed=ok))
        if not ok:
            failures.append(name)
    return {"base":base,"checks":result,"checks_passed":not failures,
        "failures":failures,"production_release_ready":False,
        "note":"Only anonymous smoke checks. Finance, backups, migrations, CRM tenant authorization, "
               "paid provider calls, data completeness and commercial release are NOT certified."}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url",required=True)
    parser.add_argument("--commercial-enabled",action="store_true")
    parser.add_argument("--expected-sha")
    args=parser.parse_args()
    report=run(args.base_url,commercial_enabled=args.commercial_enabled,expected_sha=args.expected_sha)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not report["checks_passed"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
