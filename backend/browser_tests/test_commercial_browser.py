import os
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright, expect
import pytest

URL = "http://127.0.0.1:8765"

@pytest.mark.parametrize("viewport", [{"width":1280,"height":800},{"width":390,"height":844}])
def test_commercial_workspace(viewport):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport=viewport)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(URL + "/commercial")
        page.locator('[name="organization_id"]').fill("1")
        page.locator('[name="email"]').fill("browser@example.test")
        page.locator('[name="password"]').fill("browser-test-password")
        page.get_by_role("button",name="Entrar",exact=True).click()
        expect(page.locator("#workspace")).to_be_visible()
        expect(page.get_by_role("button",name="Adicionar lead")).to_be_visible()
        page.locator('#form-area [name="name"]').fill("Lead E2E " + str(viewport["width"]))
        page.get_by_role("button",name="Adicionar lead").click()
        expect(page.locator("#results")).to_contain_text("Lead E2E " + str(viewport["width"]))
        for label,title in [("Agenda","Agenda"),("Carteiras","Carteiras financeiras"),("Contatos","Contatos institucionais"),("Configurações","Configurações"),("Inteligência da organização","Inteligência da organização"),("Meu plano","Meu plano")]:
            page.get_by_role("button",name=label,exact=True).click()
            expect(page.locator("#module-title")).to_have_text(title)
            expect(page.locator("#results")).not_to_contain_text("Carregando")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), label
        expect(page.locator("#results")).to_contain_text("Essential")
        page.get_by_role("button",name="Sair",exact=True).click()
        expect(page.locator("#login")).to_be_visible()
        expect(page.locator("#workspace")).to_be_hidden()
        assert not errors, errors
        context.close()
        browser.close()


@pytest.mark.parametrize("viewport", [{"width":1280,"height":800},{"width":390,"height":844}])
def test_owner_assistant_navigation(viewport):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=viewport)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(URL + "/")
        page.locator('#login-form [name="username"]').fill("admin")
        page.locator('#login-form [name="password"]').fill("local-ci-owner-133")
        page.get_by_role("button",name="Entrar",exact=True).click()
        expect(page.get_by_role("heading",name="Central de comando",exact=True)).to_be_visible()
        if viewport["width"] < 860:
            page.locator("#nav-toggle").click()
            expect(page.locator("#nav-toggle")).to_have_attribute("aria-expanded","true")
        page.locator('#nav [data-v="assistente"]').click()
        expect(page.get_by_role("heading",name="Assistente LeadCob",exact=True)).to_be_visible()
        expect(page.locator("#ai-form")).to_be_visible()
        expect(page.locator("#ai-form button")).to_be_disabled()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        assert not errors, errors
        browser.close()


def test_customer_journey_and_tenant_boundaries():
    with sync_playwright() as p:
        browser=p.chromium.launch()
        a=browser.new_context()
        b=browser.new_context()
        def login(context, org, email, password):
            response=context.request.post(URL+"/api/commercial/auth/login",
                headers={"Origin":URL},data=dict(organization_id=org,email=email,password=password))
            assert response.status==200, response.text()
            return {"Origin":URL,"X-CSRF-Token":response.json()["csrf_token"]}
        ha=login(a,1,"browser@example.test","browser-test-password")
        hb=login(b,2,"browser-b@example.test","browser-b-test-password")
        def path(org, suffix):
            return URL+f"/api/commercial/workspace/{org}/"+suffix
        def create(suffix,payload):
            resp=a.request.post(path(1,suffix),headers=ha,data=payload)
            assert resp.status==201,resp.text()
            return resp.json()
        lead=create("leads",dict(name="Journey private lead",notes="local test",stage="identified"))
        task=create("tasks",dict(title="Journey followup",due_date="2026-11-20"))
        portfolio=create("portfolios",dict(name="Journey private portfolio",reference_date="2026-11-17"))
        pid=portfolio["id"]
        title=create(f"portfolios/{pid}/titles",dict(reference="E2E-001",amount="123.45",due_date="2026-11-16"))
        assert title["amount"]=="123.45"
        summary=a.request.get(path(1,f"portfolios/{pid}/summary?as_of=2026-11-17"))
        assert summary.status==200
        assert summary.json()["outstanding"]=="123.45"
        assert summary.json()["overdue"]=="123.45"
        contact=create("contacts",dict(cnpj="11222333000181",kind="email",
            value="financeiro@example.test",source_url="https://example.test/contato",institutional=True))
        assert contact["status"]=="a_verificar"
        assert a.request.patch(path(1,f"tasks/{task['id']}"),headers=ha,data={"completed":True}).status==200
        assert a.request.put(path(1,f"leads/{lead['id']}"),headers=ha,
            data=dict(name=lead["name"],notes="updated",stage="contacted")).status==200
        for resource in ("leads","tasks","portfolios","contacts"):
            assert b.request.get(path(1,resource)).status==403
            assert b.request.get(path(2,resource)).json()==[]
        assert b.request.get(path(2,f"leads/{lead['id']}")).status==404
        assert b.request.get(path(2,f"portfolios/{pid}/titles")).status==404
        assert b.request.post(path(2,f"portfolios/{pid}/titles"),headers=hb,
            data=dict(reference="blocked",amount="1.00",due_date="2026-11-17")).status==404
        ctx = a.request.get(path(1,"assistant/context"))
        assert ctx.status==200,ctx.text()
        assert ctx.json()["organization_id"]==1
        assert ctx.json()["lead_stages"]["contacted"]>=1
        assert ctx.json()["portfolio_count"]==1
        assert ctx.json()["companies_by_channel"]["email"]==1
        assert ctx.json()["generation_enabled"] is False
        assert b.request.get(path(1,"assistant/context")).status==403
        other=b.request.get(path(2,"assistant/context"))
        assert other.status==200
        assert other.json()["lead_count"]==0
        assert other.json()["portfolio_count"]==0
        assert other.json()["companies_by_channel"]=={}
        assert b.request.get(URL+"/api/assistant/status").status==401
        assert b.request.get(URL+"/api/registry/qualification").status==401
        assert b.request.get(URL+"/api/owner/commercial/readiness").status==401
        assert a.request.post(path(1,"leads"),headers={"Origin":URL},data={"name":"blocked"}).status==403
        assert a.request.post(URL+"/api/commercial/auth/logout",headers=ha,
            data={"organization_id":1}).status==200
        assert a.request.get(path(1,"leads")).status==403
        a.close()
        b.close()
        browser.close()


@pytest.mark.parametrize("viewport",[{"width":1280,"height":800},{"width":390,"height":844}])
def test_owner_discovery_has_explicit_manual_queue_action(viewport):
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport=viewport)
        errors=[]
        page.on("pageerror",lambda error:errors.append(str(error)))
        page.goto(URL+"/")
        page.locator('#login-form [name="username"]').fill("admin")
        page.locator('#login-form [name="password"]').fill("local-ci-owner-133")
        page.get_by_role("button",name="Entrar",exact=True).click()
        expect(page.get_by_role("heading",name="Central de comando",exact=True)).to_be_visible()
        page.goto(URL+"/owner/discovery")
        expect(page.get_by_role("heading",name="Central de enriquecimento")).to_be_visible()
        expect(page.get_by_role("button",name="Processar 1 empresa agora")).to_have_count(1)
        expect(page.locator("#detail")).to_be_hidden()
        expect(page.locator("#create")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        assert not errors,errors
        browser.close()
