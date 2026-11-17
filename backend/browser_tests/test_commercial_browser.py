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
        for label,title in [("Agenda","Agenda"),("Carteiras","Carteiras financeiras"),("Contatos","Contatos institucionais"),("Configurações","Configurações"),("Meu plano","Meu plano")]:
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
