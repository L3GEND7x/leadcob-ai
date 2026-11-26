"""Contatos institucionais a partir do SITE OFICIAL já cadastrado na ficha da empresa.

Regras (LGPD e termos de uso):
  - só lê o site informado na ficha (nunca adivinha domínios) e, no máximo, 3 páginas de contato do mesmo domínio;
  - respeita robots.txt; sem login, CAPTCHA ou formulários;
  - guarda só e-mails do PRÓPRIO domínio da empresa e com caixa institucional (contato@, financeiro@...);
    e-mails com cara de pessoa (nome.sobrenome@) e de outros domínios são descartados;
  - todo resultado sai como "a verificar", com a URL da página de origem.
"""
from __future__ import annotations

import re
import time
from app.services.safe_http import public_client, bounded_get, validate_url
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, parse_qs, unquote
from urllib.robotparser import RobotFileParser

import httpx

UA = "LeadCobAI"
MAX_BYTES = 400_000
CONTACT_HINT = re.compile(r"contato|fale|atendimento|sac|sobre|institucional|empresa|ouvidoria|secretari|licitac|compras|financ|transparencia|contact|about", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
HREF = re.compile(r"""href\s*=\s*["']([^"'#]+)["']""", re.I)
ROLE = {"contato", "contatos", "comercial", "financeiro", "cobranca", "faleconosco", "atendimento", "sac", "adm",
        "administrativo", "administracao", "vendas", "info", "informacoes", "ouvidoria", "relacionamento", "diretoria",
        "secretaria", "licitacao", "licitacoes", "compras", "financas", "tesouraria", "controladoria", "juridico", "credito", "contasareceber", "receber", "faturamento", "contact", "sales", "finance"}


def _root(host: str) -> str:
    parts = host.lower().split(".")
    if len(parts) >= 3 and parts[-1] == "br" and parts[-2] in {"com", "net", "org", "ind", "srv", "eti", "adv", "coop", "gov", "edu"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _role_box(local: str) -> bool:
    norm = re.sub(r"[^a-z]", "", local.lower())
    return norm in ROLE


SOCIAL_HOSTS = {
    "linkedin": {"linkedin.com", "www.linkedin.com", "br.linkedin.com"},
    "instagram": {"instagram.com", "www.instagram.com"},
    "facebook": {"facebook.com", "www.facebook.com", "m.facebook.com"},
}


class PublishedHTML(HTMLParser):
    """Read explicit links and visible text, not scripts, templates or comments."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.text, self.hidden = [], [], []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript", "head"}:
            self.hidden.append(tag)
        if not self.hidden and tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


def parse_published(html):
    parser = PublishedHTML()
    parser.feed(html)
    parser.close()
    return parser


# Only explicitly labelled Brazilian institutional telephone numbers in visible text.
# Do not infer WhatsApp capability, collect unlabelled numbers or scan arbitrary IDs.
PUBLIC_PHONE = re.compile(
    r"(?<![\w])(?:telefone(?:\s+(?:comercial|institucional))?|tel\.?|central de atendimento|sac|financeiro)"
    r"\s*[:\-]\s*((?:\+55\s*)?\(\d{2}\)\s*\d{4,5}[\s-]\d{4})(?!\d)", re.I
)


def published_channels(html, source_url):
    """Extract explicit contact links published by the registered business site."""
    channels = {}
    for href in parse_published(html).links:
        try:
            link = urlparse(urljoin(source_url, href.strip()))
            if link.scheme in {"http", "https"} and link.port not in (None, 80, 443):
                continue
        except ValueError:
            continue
        kind, value = None, None
        if link.scheme.lower() == "tel":
            number = unquote(link.path).split(";")[0]
            if not re.fullmatch(r"\+?[0-9() .-]+", number):
                continue
            kind, value = "phone", re.sub(r"\D", "", number)
            if len(value) in (10, 11):
                value = "55" + value
        elif link.scheme in {"http", "https"} and not link.username and not link.password:
            host = (link.hostname or "").lower()
            if host in {"wa.me", "api.whatsapp.com", "web.whatsapp.com"}:
                number = link.path.strip("/") if host == "wa.me" else parse_qs(link.query).get("phone", [""])[0]
                if host != "wa.me" and link.path.rstrip("/") != "/send":
                    continue
                if not re.fullmatch(r"\+?[0-9]{10,13}", number):
                    continue
                kind, value = "whatsapp", number.lstrip("+")
            for platform, hosts in SOCIAL_HOSTS.items():
                if host in hosts:
                    path = link.path.strip("/")
                    parts = path.split("/")
                    if platform == "linkedin":
                        valid = len(parts) == 2 and parts[0] == "company" and bool(parts[1])
                    else:
                        valid = len(parts) == 1 and bool(path) and path.lower() not in {
                            "share", "sharer", "sharer.php", "login", "intent", "p", "reel", "stories", "dialog", "accounts", "explore", "reels", "groups", "watch", "help", "marketplace", "plugins"}
                    if valid:
                        kind, value = platform, "https://www." + platform + ".com/" + path + "/"
        if kind in {"phone", "whatsapp"} and not (10 <= len(value or "") <= 13):
            continue
        if kind and value:
            channels[(kind, value)] = {"kind": kind, "value": value, "source_url": source_url}
    for match in PUBLIC_PHONE.finditer(" ".join(parse_published(html).text)):
        number = re.sub(r"\D", "", match.group(1))
        if len(number) in (10, 11):
            number = "55" + number
        if not re.fullmatch(r"55[1-9][0-9](?:[2-5][0-9]{7}|9[0-9]{8})", number):
            continue
        channels.setdefault(("phone", number),
            {"kind": "phone", "value": number, "source_url": source_url})
    return list(channels.values())


class DiscoveryUnavailable(ValueError):
    """Stable diagnostic code; never includes the remote body, URL or exception text."""
    def __init__(self, code):
        self.code = code
        super().__init__("Pesquisa institucional indisponível: " + code)


def network_reason(exc):
    if isinstance(exc, httpx.DecodingError):
        return "content_decoding_error"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        return "connect_error"
    if isinstance(exc, httpx.HTTPError):
        return "transport_error"
    if isinstance(exc, OSError):
        return "network_os_error"
    if isinstance(exc, ValueError):
        return {
            "Redirecionamento para outro domínio bloqueado.": "redirect_blocked",
            "robots.txt não permite ler o destino.": "robots_denied",
            "Tempo máximo de leitura excedido.": "deadline",
            "Limite de tamanho ou tempo da página excedido.": "page_limit",
            "Limite de redirecionamentos excedido.": "redirect_limit",
            "Destino interno bloqueado.": "destination_blocked",
        }.get(str(exc), "invalid_response")
    return "unexpected_error"


def discover(website: str, client: httpx.Client | None = None, max_pages: int = 4) -> dict:
    website = (website or "").strip()
    if not re.match(r"^(https?://)?[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(:\d+)?(/.*)?$", website):
        raise ValueError("Site institucional inválido.")
    u = urlparse(website if "://" in website else "https://" + website)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("Site institucional inválido.")
    validate_url(u.geturl())
    base = f"{u.scheme}://{u.hostname}"
    deadline = time.monotonic() + 40
    domain = _root(u.hostname)
    own = client is None
    client = client or public_client()
    found, pages, notes, channels, reasons = {}, [], [], {}, []
    try:
        robots = RobotFileParser()
        try:
            r = bounded_get(client, base + "/robots.txt", u.hostname, deadline)
            if r.status_code not in (200, 404):
                raise DiscoveryUnavailable("robots_http_" + str(r.status_code))
            robots.parse(r.text.splitlines() if r.status_code == 200 else [])
        except DiscoveryUnavailable:
            raise
        except (httpx.HTTPError, ValueError, OSError) as exc:
            raise DiscoveryUnavailable("robots_" + network_reason(exc)) from exc
        queue, seen = [website if "://" in website else "https://" + website], set()
        while queue and len(pages) < max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            if not robots.can_fetch(UA, url):
                notes.append(f"robots.txt não permite ler {url}")
                reasons.append("robots_denied")
                continue
            try:
                resp = bounded_get(client, url, u.hostname, deadline,
                                   allow_url=lambda target: robots.can_fetch(UA, target))
            except (httpx.HTTPError, ValueError, OSError) as exc:
                reasons.append(network_reason(exc))
                notes.append(f"{url}: {type(exc).__name__}")
                continue
            if resp.status_code != 200 or "html" not in resp.headers.get("content-type", "html"):
                reasons.append("page_http_" + str(resp.status_code) if resp.status_code != 200 else "non_html")
                notes.append(f"{url}: HTTP {resp.status_code}")
                continue
            final_host = urlparse(str(resp.url)).hostname or ""
            if _root(final_host) != domain:
                notes.append(f"{url} redireciona para outro domínio ({final_host}); ignorado")
                continue
            html = resp.text[:MAX_BYTES]
            parsed = parse_published(html)
            pages.append(str(resp.url))
            for item in published_channels(html, str(resp.url)):
                channels.setdefault((item["kind"], item["value"]), item)
            mailboxes = EMAIL.findall(" ".join(parsed.text))
            for href in parsed.links:
                if href.lower().startswith("mailto:"):
                    mailboxes.extend(EMAIL.findall(unquote(href[7:].split("?", 1)[0])))
            for email in mailboxes:
                email = email.lower().rstrip(".")
                local, _, host = email.partition("@")
                if (host == u.hostname.lower().removeprefix("www.") or host == u.hostname.lower()) and _role_box(local) and email not in found:
                    found[email] = str(resp.url)
            if len(pages) == 1:   # da página inicial, seguir só links de contato do mesmo domínio
                for href in parsed.links:
                    try:
                        link = urljoin(str(resp.url), href)
                        lh = urlparse(link).hostname or ""
                    except ValueError:
                        continue
                    if _root(lh) == domain and CONTACT_HINT.search(urlparse(link).path or "") and link not in seen and len(queue) < 12 and link not in queue:
                        queue.append(link)
    finally:
        if own:
            client.close()
    return {"domain": domain, "pages_read": pages, "emails": [{"email": e, "source_url": s} for e, s in found.items()],
            "channels": list(channels.values()), "notes": notes[:10], "reason_codes": sorted(set(reasons))[:10]}
