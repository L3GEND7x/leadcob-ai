"""Additional owner release checks against an already deployed revision.

No customer data is submitted. The simulation has no persistent financial effect.
AI generation is opt-in, uses the server's existing budget reservation and audit.
Never print credentials, session tokens, customer rows, or provider payloads.
"""
import argparse
from decimal import Decimal
from getpass import getpass
import json
import re

import httpx

from app.jobs.owner_acceptance import run as read_checks
from app.jobs.release_smoke import validate_base

PRODUCTION="https://leadcob-web-production.up.railway.app"
SCENARIO=dict(valor_original=1000, vencimento="2026-01-01", data_base="2026-01-31",
              multa_pct=2, juros_mes_pct=1, desconto_pct=0, entrada=130,
              parcelas=3, juros_parcelamento_mes_pct=0)


def cents(value):
    amount=Decimal(str(value))
    if not amount.is_finite() or amount!=amount.quantize(Decimal("0.01")):
        raise ValueError("Montante inválido.")
    return amount


def finance_ok(data):
    try:
        schedule=data["cronograma"]
        return (data["dias_atraso"]==30 and len(schedule)==3
                and cents(data["multa"])==Decimal("20")
                and cents(data["juros"])==Decimal("10")
                and cents(data["valor_acordado"])==Decimal("1030")
                and cents(data["entrada"])==Decimal("130")
                and all(cents(row["valor"])==Decimal("300") for row in schedule)
                and cents(schedule[-1]["saldo"])==0
                and cents(data["total_a_receber"])==Decimal("1030"))
    except (KeyError, ValueError, TypeError, ArithmeticError):
        return False


def additional(client,base,username,password,expected_sha,ai=False):
    report={"checks":[],"session_revoked":False,"provider_generation_tested":False,
            "full_release_certified":False}
    csrf=None
    def add(name,passed,**fields):
        report["checks"].append(dict(check=name,passed=bool(passed),**fields))
    try:
        r=client.get(base+"/api/health",follow_redirects=False)
        if r.status_code!=200 or r.json().get("revision")!=expected_sha:
            add("revision",False)
            return report
        r=client.post(base+"/api/auth/login",json={"username":username,"password":password},
                      headers={"Origin":base},follow_redirects=False)
        body=r.json() if r.status_code==200 else {}
        csrf=body.get("csrf_token")
        if body.get("authenticated") is not True or not isinstance(csrf,str) or not csrf:
            add("login",False,status=r.status_code)
            return report
        add("login",True)
        headers={"Origin":base,"X-CSRF-Token":csrf}
        for name,path in (("tasks","/api/tasks"),("portfolios","/api/portfolios"),
                          ("reports","/api/reports/summary"),("assistant_history","/api/assistant/conversations")):
            try:
                r=client.get(base+path,follow_redirects=False)
                add(name,r.status_code==200 and isinstance(r.json(),(list,dict)),status=r.status_code)
            except (httpx.HTTPError,ValueError,TypeError):
                add(name,False)
        r=client.post(base+"/api/negotiation/simulate",json=SCENARIO,headers=headers,follow_redirects=False)
        add("finance_synthetic",r.status_code==200 and finance_ok(r.json()),status=r.status_code)
        if ai:
            r=client.post(base+"/api/assistant/provider-check",json={},headers=headers,follow_redirects=False)
            model=r.status_code==200 and r.json().get("model_accessible") is True
            add("ai_model",model,status=r.status_code)
            if model:
                report["provider_generation_tested"]=True
                r=client.post(base+"/api/assistant/generation-check",json={},headers=headers,follow_redirects=False)
                add("ai_generation",r.status_code==200 and r.json().get("generation_passed") is True,
                    status=r.status_code)
            else:
                add("ai_generation",False,reason="model_not_verified")
    except (httpx.HTTPError,ValueError,AttributeError,TypeError):
        add("connection_or_protocol",False)
    finally:
        if isinstance(csrf,str) and csrf:
            try:
                r=client.post(base+"/api/auth/logout",headers={"Origin":base,"X-CSRF-Token":csrf},follow_redirects=False)
                s=client.get(base+"/api/auth/session",follow_redirects=False)
                report["session_revoked"]=r.status_code==200 and s.status_code==200 and s.json().get("authenticated") is False
            except (httpx.HTTPError,ValueError,AttributeError,TypeError):
                pass
            add("logout",report["session_revoked"])
        report["checks_passed"]=bool(report["checks"]) and all(c["passed"] for c in report["checks"])
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-sha",required=True)
    p.add_argument("--test-ai",action="store_true",help="Autoriza uma geração sintética sujeita ao orçamento da API.")
    a=p.parse_args()
    if not re.fullmatch("[0-9a-f]{40}",a.expected_sha):
        p.error("Informe o SHA completo.")
    base=validate_base(PRODUCTION)
    username=input("Usuário proprietário: ")
    password=getpass("Senha (não exibida): ")
    with httpx.Client(timeout=45,follow_redirects=False,trust_env=False) as client:
        first=read_checks(client,base,username,password,a.expected_sha)
        if first["checks_passed"]:
            second=additional(client,base,username,password,a.expected_sha,ai=a.test_ai)
        else:
            second={"checks_passed":False,"reason":"owner_read_checks_failed"}
    result=dict(read_checks=first,additional_checks=second,full_release_certified=False)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not first["checks_passed"] or not second["checks_passed"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
