"""Isolated Chromium owner acceptance. Only synthetic empty SQLite, never production."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright, expect
from app.core.security import password_hash

BASE="http://127.0.0.1:8765"
ART=Path("/tmp/owner-browser-artifacts")
ROUTES=(
    ("inicio","Central de comando"),("hoje","Cinco empresas para trabalhar hoje"),
    ("empresas","Encontrar empresas"),("contatos","Contatos empresariais"),
    ("crm","CRM comercial"),("cobranca","Inteligência de cobrança"),
    ("negociacao","Laboratório de negociação"),
    ("relatorios","Relatórios"),("radar","Radar de mercado"),
)


def check(browser, width,height,password):
    context=browser.new_context(viewport={"width":width,"height":height},is_mobile=width<600,
                                has_touch=width<600)
    page=context.new_page()
    errors=[]
    page.on("pageerror",lambda exc: errors.append(type(exc).__name__))
    try:
        page.goto(BASE,wait_until="domcontentloaded")
        expect(page.locator("#login-form")).to_be_visible(timeout=15000)
        page.locator('#login-form input[name="username"]').fill("owner-ci")
        page.locator('#login-form input[name="password"]').fill(password)
        page.locator("#login-form button").click()
        expect(page.locator("#view h1")).to_have_text("Central de comando",timeout=20000)
        expect(page.locator('#nav a[data-v="assistente"]')).to_have_count(0)
        expect(page.locator('script[src="/static/assistant.js"]')).to_have_count(0)
        expect(page.locator("#municipal-command-results")).to_contain_text("CNPJs válidos únicos",timeout=20000)
        page.evaluate("location.hash = '#/assistente'")
        page.wait_for_function("location.hash === '#/inicio'")
        expect(page.locator("#view h1")).to_have_text("Central de comando",timeout=20000)
        for route,title in ROUTES:
            if width<600:
                toggle=page.locator("#nav-toggle")
                expect(toggle).to_be_visible()
                if toggle.get_attribute("aria-expanded")!="true":
                    toggle.click()
            page.locator(f'#nav a[data-v="{route}"]').click()
            expect(page.locator("#view h1")).to_have_text(title,timeout=20000)
            if width<600:
                expect(page.locator("#nav-toggle")).to_have_attribute("aria-expanded","false")
            page.screenshot(path=str(ART/f"{width}-{route}.png"),animations="disabled")
            if page.evaluate("document.documentElement.scrollWidth > innerWidth + 2"):
                raise AssertionError(f"Document overflow on {route} at {width}px")
        if errors:
            raise AssertionError(f"Uncaught JavaScript errors: {len(errors)}")
    finally:
        context.close()


def main():
    if os.getenv("DATABASE_URL")!="sqlite:////tmp/leadcob-owner-browser.sqlite" or os.getenv("APP_ENV")!="development":
        raise RuntimeError("Only dedicated synthetic CI environment is allowed.")
    ART.mkdir(exist_ok=True)
    password=secrets.token_urlsafe(24)
    env=dict(os.environ,ADMIN_PASSWORD_HASH=password_hash(password),
             ADMIN_USERNAME="owner-ci",OPENAI_API_KEY="",DEMO_SEED="false")
    with (ART/"server.log").open("w") as log:
        process=subprocess.Popen([sys.executable,"-m","uvicorn","app.main:app",
                                  "--host","127.0.0.1","--port","8765"],env=env,stdout=log,stderr=log)
        try:
            for _ in range(60):
                try:
                    with urllib.request.urlopen(BASE+"/api/health",timeout=1) as response:
                        if response.status==200:
                            break
                except OSError:
                    time.sleep(1)
            else:
                raise RuntimeError("Synthetic server failed to start.")
            with sync_playwright() as p:
                browser=p.chromium.launch()
                try:
                    check(browser,1440,900,password)
                    check(browser,390,844,password)
                finally:
                    browser.close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__=="__main__":
    main()
