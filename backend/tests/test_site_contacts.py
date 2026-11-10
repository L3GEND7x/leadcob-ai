"""Busca de contatos no site oficial: só e-mails institucionais do próprio domínio, respeitando robots.txt."""
import httpx

from app.collectors.site_contacts import discover

HOME = """<html><a href="/fale-conosco">Fale conosco</a><a href="https://outro.com/contato">x</a>
contato@empresa.com.br joao.silva@empresa.com.br vendas@gmail.com</html>"""
CONTACT = "<p>Financeiro: financeiro@empresa.com.br · SAC: sac@empresa.com.br</p>"


def handler(request: httpx.Request):
    path = request.url.path
    if path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nDisallow: /privado\n")
    if path in ("/", ""):
        return httpx.Response(200, text=HOME, headers={"content-type": "text/html"})
    if path == "/fale-conosco":
        return httpx.Response(200, text=CONTACT, headers={"content-type": "text/html"})
    return httpx.Response(404)


def test_only_role_emails_from_own_domain():
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    r = discover("https://www.empresa.com.br/", client=client)
    emails = {e["email"] for e in r["emails"]}
    assert emails == {"contato@empresa.com.br", "financeiro@empresa.com.br", "sac@empresa.com.br"}
    assert "joao.silva@empresa.com.br" not in emails and "vendas@gmail.com" not in emails   # pessoa e outro domínio
    assert all(e["source_url"].startswith("https://www.empresa.com.br") for e in r["emails"])
    assert len(r["pages_read"]) == 2   # página inicial + fale conosco; link externo ignorado


def test_respects_robots():
    def deny(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(200, text=HOME, headers={"content-type": "text/html"})
    r = discover("https://empresa.com.br", client=httpx.Client(transport=httpx.MockTransport(deny)))
    assert r["emails"] == [] and r["pages_read"] == [] and "robots.txt" in r["notes"][0]


def test_invalid_site():
    import pytest
    with pytest.raises(ValueError):
        discover("javascript:alert(1)")
