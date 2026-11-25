"""Owner acceptance check: real HTTPS session, GET-only business routes, aggregate results.

Credentials are entered locally, never stored or logged. Only login/logout write
session state. No provider requests, CRM changes, or financial actions.
"""
import argparse
from getpass import getpass
import json
import re
import time

import httpx

from app.jobs.release_smoke import validate_base

CHECKS = (
    ("command_center", "/api/command-center"),
    ("daily_intelligence", "/api/daily-intelligence?limit=1"),
    ("company_search", "/api/companies/search?uf=AM&page=1&per_page=1"),
    ("registry", "/api/registry/coverage?uf=AM&city=Manaus"),
    ("qualification", "/api/registry/qualification?uf=AM&city=Manaus&limit=1"),
    ("contactability", "/api/contacts/contactability?uf=AM&city=Manaus"),
    ("pipeline", "/api/pipeline"),
    ("assistant", "/api/assistant/status"),
    ("commercial_readiness", "/api/owner/commercial/readiness"),
)


def integers(data, keys):
    return isinstance(data, dict) and all(type(data.get(k)) is int and data[k]>=0 for k in keys)


def verify(name, data):
    metrics={}
    if name=="registry":
        keys=("company_records","missing_cnpj_records","invalid_cnpj_records","valid_cnpj_records",
              "unique_valid_cnpjs","duplicate_valid_records","active_cnpjs","inactive_cnpjs",
              "unknown_status_cnpjs","conflicting_status_cnpjs")
        ok=integers(data,keys)
        if ok:
            m={k:data[k] for k in keys}
            ok=(m["company_records"]==m["missing_cnpj_records"]+m["invalid_cnpj_records"]+m["valid_cnpj_records"]
                and m["valid_cnpj_records"]==m["unique_valid_cnpjs"]+m["duplicate_valid_records"]
                and m["unique_valid_cnpjs"]==sum(m[k] for k in keys[-4:]))
            metrics=m
        return ok,metrics
    if name=="contactability":
        keys=("valid_unique_cnpjs","active_unique_cnpjs","active_corporate_cnpjs",
              "with_any_direct_channel","with_verified_direct_channel",
              "with_verified_sourced_direct_channel","without_direct_channel")
        ok=integers(data,keys)
        if ok:
            metrics={k:data[k] for k in keys}
            v,a,c,d,w,s,n=[metrics[k] for k in keys]
            ok=0<=s<=w<=d<=c<=a<=v and d+n==c
        return ok,metrics
    if name=="qualification":
        ok=integers(data,("unique_cnpjs","total")) and isinstance(data.get("counts"),dict)
        if ok:
            values=data["counts"].values()
            ok=all(type(v) is int and v>=0 for v in values) and sum(values)==data["unique_cnpjs"]
            ok=ok and data["total"]==data["unique_cnpjs"] and isinstance(data.get("items"),list) and len(data["items"])<=1
            metrics={"unique_cnpjs":data["unique_cnpjs"]}
        return ok,metrics
    if name=="assistant":
        checks=data.get("configuration_checks") if isinstance(data,dict) else None
        ok=isinstance(checks,dict) and all(checks.get(k) is True for k in
                    ("api_key","model","monthly_budget","input_price","output_price")) and data.get("configured") is True
        return ok,{"provider_verified":False,"configured":ok}
    if not isinstance(data,(dict,list)):
        return False,{}
    if name=="command_center":
        return isinstance(data,dict) and integers(data.get("kpis"),("empresas_total","leads_qualificados")),{}
    if name=="pipeline":
        return isinstance(data,dict) and isinstance(data.get("stages"),list),{}
    if name=="company_search":
        return isinstance(data,dict) and isinstance(data.get("items"),list),{}
    return True,{}


def run(client, base, username, password, expected_sha):
    base=validate_base(base)
    if not base.startswith("https://") or not re.fullmatch(r"[0-9a-f]{40}",expected_sha):
        raise ValueError("Exige HTTPS e SHA completo em minúsculas.")
    result={"expected_sha":expected_sha,"checks":[],"session_revoked":False,
            "owner_release_ready":False,"provider_verified":False}
    csrf=None
    def record(name,ok,**fields):
        result["checks"].append(dict(check=name,passed=bool(ok),**fields))
    try:
        health=client.get(base+"/api/health",follow_redirects=False)
        body=health.json() if health.status_code==200 else {}
        same=body.get("status")=="ok" and body.get("revision")==expected_sha
        record("deployed_revision",same,status=health.status_code)
        if not same:
            return result
        login=client.post(base+"/api/auth/login",json={"username":username,"password":password},
                          headers={"Origin":base},follow_redirects=False)
        body=login.json() if login.status_code==200 else {}
        csrf=body.get("csrf_token")
        ok=body.get("authenticated") is True and isinstance(csrf,str) and bool(csrf)
        record("login",ok,status=login.status_code)
        if not ok:
            return result
        session=client.get(base+"/api/auth/session",follow_redirects=False)
        record("session",session.status_code==200 and session.json().get("authenticated") is True,
               status=session.status_code)
        for name,path in CHECKS:
            start=time.monotonic()
            try:
                response=client.get(base+path,follow_redirects=False)
                ok,metrics=verify(name,response.json()) if response.status_code==200 else (False,{})
                record(name,ok,status=response.status_code,seconds=round(time.monotonic()-start,3),metrics=metrics)
            except (ValueError,httpx.HTTPError,TypeError,AttributeError):
                record(name,False)
    except (ValueError,httpx.HTTPError,TypeError,AttributeError):
        record("connection_or_protocol",False)
    finally:
        if isinstance(csrf,str) and csrf:
            try:
                response=client.post(base+"/api/auth/logout",headers={"Origin":base,"X-CSRF-Token":csrf},
                                     follow_redirects=False)
                session=client.get(base+"/api/auth/session",follow_redirects=False)
                result["session_revoked"]=response.status_code==200 and session.status_code==200 and session.json().get("authenticated") is False
            except (ValueError,httpx.HTTPError,TypeError,AttributeError):
                pass
            record("logout",result["session_revoked"])
        result["checks_passed"]=bool(result["checks"]) and all(x["passed"] for x in result["checks"])
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url",default="https://leadcob-web-production.up.railway.app")
    p.add_argument("--expected-sha",required=True)
    a=p.parse_args()
    username=input("Usuário proprietário: ")
    password=getpass("Senha (não exibida): ")
    with httpx.Client(timeout=30,follow_redirects=False,trust_env=False) as client:
        report=run(client,a.base_url,username,password,a.expected_sha)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not report["checks_passed"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
