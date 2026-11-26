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


def test_published_business_channels_and_share_links():
    from app.collectors.site_contacts import published_channels
    html = """<a href="tel:+55 (92) 3232-4040">Ligar</a>
    <a href="https://wa.me/5592999999999?text=oi">WhatsApp</a>
    <a href="https://www.linkedin.com/company/exemplo/">LinkedIn</a>
    <a href="https://www.linkedin.com/in/pessoa/">Pessoa</a>
    <a href="https://instagram.com/empresa/">Instagram</a>
    <a href="https://facebook.com/empresa/">Facebook</a>
    <a href="https://facebook.com/sharer.php?u=x">Compartilhar</a>
    <a href="https://www.linkedin.com.evil.test/company/exemplo/">Falso</a>
    <a href="https://wa.me/abc">Inválido</a>"""
    rows = published_channels(html, "https://empresa.com.br/contato")
    assert {x["kind"] for x in rows} == {"phone", "whatsapp", "linkedin", "instagram", "facebook"}
    assert len(rows) == 5
    assert all(x["source_url"] == "https://empresa.com.br/contato" for x in rows)
    assert next(x["value"] for x in rows if x["kind"] == "phone") == "559232324040"


def test_published_mailto_and_hidden_content():
    html = """<html><head><script>var email='vendas@empresa.com.br';</script></head>
    <body><!-- sac@empresa.com.br -->
    <a href=mailto:financeiro%40empresa.com.br?subject=Oi>Financeiro</a>
    <p>contato&#64;empresa.com.br</p>
    <template>compras@empresa.com.br</template>
    <a href='mailto:joao.silva@empresa.com.br'>Pessoa</a>
    <a href='mailto:info@outro.empresa.com.br'>Outro host</a>
    <a href='https://wa.me/abc5592999999999'>Inválido</a>
    <a href='https://api.whatsapp.com/send?phone=5592999999999&amp;text=Oi'>WhatsApp</a>
    <a href='https://instagram.com/accounts/'>Login</a>
    <a href='https://linkedin.com/company/empresa/'>LinkedIn</a>
    <a href='http://[invalid'>URL inválida</a>
    </body></html>"""
    def response(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200,text=html,headers={"content-type":"text/html"})
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        r=discover("https://www.empresa.com.br/",client=client)
    assert {e["email"] for e in r["emails"]}=={"financeiro@empresa.com.br","contato@empresa.com.br"}
    assert {(e["kind"],e["value"]) for e in r["channels"]}=={
        ("whatsapp","5592999999999"),("linkedin","https://www.linkedin.com/company/empresa/")}
    assert all(e["source_url"]=="https://www.empresa.com.br/" for e in r["emails"]+r["channels"])


def test_labelled_phones_without_inferred_whatsapp():
    from app.collectors.site_contacts import published_channels
    html = """<p>Telefone comercial: (92) 3232-4040</p>
    <p>Financeiro: (92) 99999-8888</p>
    <a href="tel:9232324040">Ligar</a>
    <p>Pedido (92) 3333-4444</p>
    <script>Telefone: (92) 3555-5555</script>
    <a href="tel:abc9233334444">Inválido</a>"""
    source="https://empresa.example/contato"
    channels=published_channels(html,source)
    assert {(c["kind"],c["value"]) for c in channels}=={
        ("phone","559232324040"),("phone","5592999998888")}
    assert all(c["source_url"]==source for c in channels)


def test_robots_applies_before_following_same_host_redirect():
    requested = []

    def redirect_to_blocked(request):
        requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: LeadCobAI\nDisallow: /privado\n")
        if request.url.path == "/":
            return httpx.Response(302, headers={"location": "/privado/contato"})
        raise AssertionError("Blocked destination must not receive a request")

    with httpx.Client(transport=httpx.MockTransport(redirect_to_blocked)) as client:
        result = discover("https://empresa.example/", client=client)
    assert requested == ["/robots.txt", "/"]
    assert result["pages_read"] == [] and result["emails"] == [] and result["channels"] == []


def test_allowed_same_host_redirect_still_collects():
    requested = []

    def redirect_to_allowed(request):
        requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: LeadCobAI\nDisallow: /privado\n")
        if request.url.path == "/":
            return httpx.Response(302, headers={"location": "/contato"})
        return httpx.Response(200, text="<p>financeiro@empresa.example</p>", headers={"content-type":"text/html"})

    with httpx.Client(transport=httpx.MockTransport(redirect_to_allowed)) as client:
        result = discover("https://empresa.example/", client=client)
    assert requested == ["/robots.txt", "/", "/contato"]
    assert result["emails"] == [{"email":"financeiro@empresa.example", "source_url":"https://empresa.example/contato"}]


def test_robots_http_and_transport_errors_have_safe_reason_codes():
    import pytest
    from app.collectors.site_contacts import DiscoveryUnavailable
    for status in (403, 429, 503):
        seen = []
        def handler(request):
            seen.append(request.url.path)
            return httpx.Response(status, text="private response body")
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(DiscoveryUnavailable) as exc:
                discover("https://empresa.example/contato", client=client)
        assert exc.value.code == f"robots_http_{status}"
        assert "private response body" not in str(exc.value)
        assert seen == ["/robots.txt"]
    def timeout(request):
        raise httpx.ConnectTimeout("do not expose")
    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(DiscoveryUnavailable) as exc:
            discover("https://empresa.example/", client=client)
    assert exc.value.code == "robots_timeout"
    assert "do not expose" not in str(exc.value)


def test_denied_content_reports_reason_without_fetching():
    seen = []
    def handler(request):
        seen.append(request.url.path)
        assert request.url.path == "/robots.txt"
        return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report = discover("https://empresa.example/", client=client)
    assert seen == ["/robots.txt"]
    assert report["reason_codes"] == ["robots_denied"]
    assert not report["emails"] and not report["pages_read"]
