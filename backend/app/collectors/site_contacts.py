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
from urllib.parse import urljoin, urlparse, parse_qs, unquote
from urllib.robotparser import RobotFileParser

import httpx

UA = "LeadCobAI/0.5 (contato institucional; respeita robots.txt)"
MAX_BYTES = 400_000
CONTACT_HINT = re.compile(r"contato|fale|atendimento|sac|sobre|institucional|empresa|ouvidoria|contact|about", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
HREF = re.compile(r"""href\s*=\s*["']([^"'#]+)["']""", re.I)
ROLE = {"contato", "contatos", "comercial", "financeiro", "cobranca", "faleconosco", "atendimento", "sac", "adm",
        "administrativo", "administracao", "vendas", "info", "informacoes", "ouvidoria", "relacionamento", "diretoria",
        "secretaria", "juridico", "credito", "contasareceber", "receber", "faturamento", "contact", "sales", "finance"}


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


def published_channels(html, source_url):
    """Extract explicit contact links published by the registered business site."""
    channels = {}
    for href in HREF.findall(html):
        link = urlparse(urljoin(source_url, href.strip()))
        kind, value = None, None
        if link.scheme.lower() == "tel":
            kind, value = "phone", re.sub(r"\D", "", unquote(link.path).split(";")[0])
        elif link.scheme in {"http", "https"} and not link.username and not link.password:
            host = (link.hostname or "").lower()
            if host in {"wa.me", "api.whatsapp.com", "web.whatsapp.com"}:
                number = link.path.strip("/") if host == "wa.me" else parse_qs(link.query).get("phone", [""])[0]
                kind, value = "whatsapp", re.sub(r"\D", "", number)
            for platform, hosts in SOCIAL_HOSTS.items():
                if host in hosts:
                    path = link.path.strip("/")
                    parts = path.split("/")
                    if platform == "linkedin":
                        valid = len(parts) == 2 and parts[0] == "company" and bool(parts[1])
                    else:
                        valid = len(parts) == 1 and bool(path) and path.lower() not in {
                            "share", "sharer", "sharer.php", "login", "intent", "p", "reel", "stories", "dialog"}
                    if valid:
                        kind, value = platform, "https://www." + platform + ".com/" + path + "/"
        if kind in {"phone", "whatsapp"} and not (10 <= len(value or "") <= 13):
            continue
        if kind and value:
            channels[(kind, value)] = {"kind": kind, "value": value, "source_url": source_url}
    return list(channels.values())


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
    found, pages, notes, channels = {}, [], [], {}
    try:
        robots = RobotFileParser()
        try:
            r = bounded_get(client, base + "/robots.txt", u.hostname, deadline)
            if r.status_code not in (200, 404):
                raise ValueError("Não foi possível verificar robots.txt.")
            robots.parse(r.text.splitlines() if r.status_code == 200 else [])
        except (httpx.HTTPError, ValueError) as exc:
            raise ValueError("Não foi possível verificar robots.txt.") from exc
        queue, seen = [website if "://" in website else "https://" + website], set()
        while queue and len(pages) < max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            if not robots.can_fetch(UA, url):
                notes.append(f"robots.txt não permite ler {url}")
                continue
            try:
                resp = bounded_get(client, url, u.hostname, deadline)
            except (httpx.HTTPError, ValueError) as exc:
                notes.append(f"{url}: {type(exc).__name__}")
                continue
            if resp.status_code != 200 or "html" not in resp.headers.get("content-type", "html"):
                notes.append(f"{url}: HTTP {resp.status_code}")
                continue
            final_host = urlparse(str(resp.url)).hostname or ""
            if _root(final_host) != domain:
                notes.append(f"{url} redireciona para outro domínio ({final_host}); ignorado")
                continue
            html = unescape(resp.text[:MAX_BYTES])
            pages.append(str(resp.url))
            for item in published_channels(html, str(resp.url)):
                channels.setdefault((item["kind"], item["value"]), item)
            for email in EMAIL.findall(html):
                email = email.lower().rstrip(".")
                local, _, host = email.partition("@")
                if _root(host) == domain and _role_box(local) and email not in found:
                    found[email] = str(resp.url)
            if len(pages) == 1:   # da página inicial, seguir só links de contato do mesmo domínio
                for href in HREF.findall(html):
                    link = urljoin(str(resp.url), href)
                    lh = urlparse(link).hostname or ""
                    if _root(lh) == domain and CONTACT_HINT.search(urlparse(link).path or "") and link not in seen and len(queue) < 12:
                        queue.append(link)
    finally:
        if own:
            client.close()
    return {"domain": domain, "pages_read": pages, "emails": [{"email": e, "source_url": s} for e, s in found.items()],
            "channels": list(channels.values()), "notes": notes[:10]}
