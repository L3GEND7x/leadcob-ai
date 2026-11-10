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
from html import unescape
from urllib.parse import urljoin, urlparse
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
    return norm in ROLE or any(norm.startswith(r) for r in ROLE)


def discover(website: str, client: httpx.Client | None = None, max_pages: int = 4) -> dict:
    website = (website or "").strip()
    if not re.match(r"^(https?://)?[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(:\d+)?(/.*)?$", website):
        raise ValueError("Site institucional inválido.")
    u = urlparse(website if "://" in website else "https://" + website)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("Site institucional inválido.")
    base = f"{u.scheme}://{u.hostname}"
    domain = _root(u.hostname)
    own = client is None
    client = client or httpx.Client(timeout=12.0, follow_redirects=True, headers={"User-Agent": UA})
    found, pages, notes = {}, [], []
    try:
        robots = RobotFileParser()
        try:
            r = client.get(base + "/robots.txt")
            robots.parse(r.text.splitlines() if r.status_code == 200 else [])
        except httpx.HTTPError:
            robots.parse([])
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
                resp = client.get(url)
            except httpx.HTTPError as exc:
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
            for email in EMAIL.findall(html):
                email = email.lower().rstrip(".")
                local, _, host = email.partition("@")
                if _root(host) == domain and _role_box(local) and email not in found:
                    found[email] = str(resp.url)
            if len(pages) == 1:   # da página inicial, seguir só links de contato do mesmo domínio
                for href in HREF.findall(html):
                    link = urljoin(str(resp.url), href)
                    lh = urlparse(link).hostname or ""
                    if _root(lh) == domain and CONTACT_HINT.search(urlparse(link).path or "") and link not in seen:
                        queue.append(link)
    finally:
        if own:
            client.close()
    return {"domain": domain, "pages_read": pages, "emails": [{"email": e, "source_url": s} for e, s in found.items()],
            "notes": notes[:10]}
