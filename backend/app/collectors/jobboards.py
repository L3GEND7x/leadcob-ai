"""Vagas publicadas em career boards Greenhouse e Lever (APIs públicas documentadas).

- Greenhouse Job Board API: GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
  (documentação: https://docs.greenhouse.io/job-board — GET público, sem autenticação)
- Lever Postings API: GET https://api.lever.co/v0/postings/{site}?mode=json&skip=&limit=
  (documentação: https://github.com/lever/postings-api)

Não são buscadores do mercado: cada board pertence a UMA empresa e precisa ser
configurado. Em 09/11/2026, de 46 (Greenhouse) e 31 (Lever) identificadores de empresas brasileiras
testados, 12 tinham board no Greenhouse e 2 no Lever — quase todos bancos
e fintechs. A maior parte dos empregadores brasileiros usa outras plataformas.
Ideia original do conector: pacote LeadCob v0.3; revisado com dados reais.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

import httpx

from app.services.jobs import classify_job, strip_html

CONFIG_FILE = Path(os.getenv("JOB_BOARDS_FILE", Path(__file__).resolve().parents[3] / "config" / "job_boards.json"))
PROVIDERS = {"greenhouse", "lever"}
LEVER_PAGE = 100


def configured_boards(raw: str | None = None, path: Path | None = None) -> list[dict]:
    """Boards do arquivo config/job_boards.json + variável JOB_BOARD_SOURCES_JSON (formato da v0.3)."""
    boards: list[dict] = []
    path = path or CONFIG_FILE
    if path and Path(path).exists():
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        boards.extend(data.get("boards", []) if isinstance(data, dict) else data)
    raw = os.getenv("JOB_BOARD_SOURCES_JSON", "") if raw is None else raw
    if raw.strip():
        try:
            extra = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JOB_BOARD_SOURCES_JSON inválido: {exc}") from exc
        if not isinstance(extra, list):
            raise ValueError("JOB_BOARD_SOURCES_JSON deve ser uma lista")
        boards.extend(extra)
    seen, out = set(), []
    for b in boards:
        if not isinstance(b, dict) or b.get("provider") not in PROVIDERS or not b.get("token") or not b.get("company_name"):
            raise ValueError("Cada board precisa de provider (greenhouse|lever), token e company_name")
        key = (b["provider"], b["token"])
        if key not in seen:
            seen.add(key); out.append(b)
    return out


def _get(client: httpx.Client, url: str, params: dict, attempts: int = 3):
    last = None
    for i in range(attempts):
        try:
            r = client.get(url, params=params)
            if r.status_code == 404:
                raise LookupError("board não encontrado (404) — token mudou ou board foi desativado")
            r.raise_for_status()
            return r.json()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last = exc
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500 and exc.response.status_code != 429:
                break
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{type(last).__name__}: {str(last)[:160]}")


def fetch_board(client: httpx.Client, board: dict) -> list[dict]:
    if board["provider"] == "greenhouse":
        data = _get(client, f"https://boards-api.greenhouse.io/v1/boards/{board['token']}/jobs", {"content": "true"})
        return [{"id": j.get("id"), "title": j.get("title") or "", "location": (j.get("location") or {}).get("name") or "",
                 "description": strip_html(j.get("content") or ""), "url": j.get("absolute_url") or "",
                 "published": j.get("first_published") or j.get("updated_at")} for j in data.get("jobs", [])]
    jobs, skip = [], 0
    while True:
        page = _get(client, f"https://api.lever.co/v0/postings/{board['token']}", {"mode": "json", "skip": skip, "limit": LEVER_PAGE})
        if not isinstance(page, list):
            break
        for j in page:
            cat = j.get("categories") or {}
            jobs.append({"id": j.get("id"), "title": j.get("text") or "", "location": cat.get("location") or "",
                         "description": strip_html(j.get("descriptionPlain") or j.get("description") or ""),
                         "url": j.get("hostedUrl") or j.get("applyUrl") or "", "published": j.get("createdAt")})
        if len(page) < LEVER_PAGE:
            break
        skip += LEVER_PAGE
    return jobs


def fetch_job_opportunities(boards: list[dict] | None = None) -> dict:
    boards = configured_boards() if boards is None else boards
    records, errors, discarded, fetched_boards, total = [], [], [], [], 0
    with httpx.Client(timeout=30, headers={"Accept": "application/json", "User-Agent": "LeadCobAI/0.3 (vagas publicas)"}) as client:
        for board in boards:
            try:
                jobs = fetch_board(client, board)
            except Exception as exc:
                errors.append({"company": board["company_name"], "provider": board["provider"], "error": str(exc)[:200]})
                continue
            fetched_boards.append(f"job:{board['provider']}:{board['token']}:")
            total += len(jobs)
            for job in jobs:
                url = job["url"].strip()
                if not job["title"] or not url.startswith("https://"):
                    continue
                result = classify_job(job["title"], job["description"], job["location"])
                if result["relevance"] == "descartar":
                    if result["relevance_reason"] != "vaga sem relação com cobrança" and len(discarded) < 15:
                        discarded.append({"empresa": board["company_name"], "vaga": job["title"][:120], "motivo": result["relevance_reason"]})
                    continue
                key = (f"job:{board['provider']}:{board['token']}:{job['id']}" if job["id"]
                       else "job:" + hashlib.sha256((url + job["title"]).encode()).hexdigest())
                records.append({**result, "source_key": key, "provider": board["provider"], "board": board,
                                "company_name": board["company_name"], "cnpj": re.sub(r"[^0-9A-Za-z]", "", str(board.get("cnpj") or "")).upper() or None,
                                "title": job["title"][:250], "location": job["location"], "description": job["description"][:5000],
                                "url": url, "published": job["published"]})
    return {"records": records, "boards_configured": len(boards), "boards_fetched": fetched_boards,
            "jobs_read": total, "discarded_samples": discarded, "errors": errors}
