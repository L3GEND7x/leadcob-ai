"""Gera a página estática do LeadCob (dados reais) para publicação privada.

Uso (na raiz do repositório):
    python scripts/build_dashboard_snapshot.py --out painel.html [--previous pagina_anterior.html]
        [--uf AM,PA] [--trigger trig_...] [--crm pasta_exportada_do_banco_da_pagina]

Passos:
 1. cria um banco temporário e carrega as empresas da página anterior (base CNPJ da Receita e
    empresas já trabalhadas no CRM), antes das captações, para os ids ficarem estáveis;
 2. roda as captações ao vivo (PNCP, vagas Greenhouse/Lever, DataJud por UF);
 3. reaplica, na ordem e com a hora original, as ações do CRM gravadas na página publicada
    (coleção `crm_eventos` do banco da página, exportada para --crm);
 4. lê tudo pela própria API e embute num HTML único com o frontend do projeto.
Falha de uma fonte não derruba as outras: o erro vai para o aviso do topo da página.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPANY_FIELDS = ["name", "trade_name", "cnpj", "segment", "city", "state", "website", "institutional_email", "cnae_main",
                  "cnae_desc", "cnae_secondary", "registration_status", "company_size", "legal_nature", "capital_social",
                  "opened_at", "target_profile", "registry_source"]
FICHAS_MAX = 600     # fichas completas embutidas (o restante abre pelo resumo)
APPROACHES_MAX = 300


def previous_data(path: str | None) -> dict:
    if not path or not Path(path).exists():
        return {}
    m = re.search(r"window\.__DEMO = (\{.*?\});</script>", Path(path).read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1)) if m else {}


def load_crm(path: str | None) -> tuple[list[dict], list[dict]]:
    """{"eventos": [{id, em, tipo, chave, dados}], "oportunidades_manuais": [{_doc, ...}]} (ou só a lista de eventos)."""
    if not path or not Path(path).exists():
        return [], []
    if Path(path).is_dir():   # exportação do banco da página: <dir>/<coleção>/<doc_id>.json
        read = lambda sub, key: [{**json.loads(f.read_text(encoding="utf-8")), key: f.stem}
                                 for f in sorted((Path(path) / sub).glob("*.json"))]
        raw = {"eventos": read("crm_eventos", "id"), "oportunidades_manuais": read("oportunidades_manuais", "_doc")}
    else:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    events = raw.get("eventos", []) if isinstance(raw, dict) else raw
    manual = raw.get("oportunidades_manuais", []) if isinstance(raw, dict) else []
    events = sorted((e for e in events if isinstance(e, dict) and e.get("tipo")), key=lambda e: (e.get("em") or "", e.get("id") or ""))
    return events, [m for m in manual if isinstance(m, dict) and m.get("_doc")]


def parse_iso(v):
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def rows_from_json(paths: list[str] | None) -> list[dict]:
    """Bases exportadas por scripts/export_base.py (ramo dados-cnpj): {"empresas": [...]}."""
    out = []
    for path in paths or []:
        if Path(path).exists():
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            out += [{k: v for k, v in r.items() if k in COMPANY_FIELDS + ["registry_updated_at", "created_at"]}
                    for r in data.get("empresas", [])]
    return out


def rows_from_db(path: str | None) -> list[dict]:
    """Empresas de outro banco do LeadCob (ex.: importação da Receita feita à parte), só campos de PJ."""
    if not path or not Path(path).exists():
        return []
    import sqlite3
    con = sqlite3.connect(path); con.row_factory = sqlite3.Row
    cols = {r[1] for r in con.execute("PRAGMA table_info(companies)")}
    want = [c for c in COMPANY_FIELDS + ["registry_updated_at", "created_at"] if c in cols]
    rows = [dict(r) for r in con.execute(f"SELECT {', '.join(want)} FROM companies WHERE cnpj IS NOT NULL ORDER BY id")]
    con.close()
    return rows


def seed_companies(prev: dict, extra: list[dict] | None = None):
    from app.db.database import SessionLocal
    from app.db.models import Company
    rows = prev.get("prospects_all", []) + (extra or [])
    with SessionLocal() as db:
        seen = set()
        for p in rows:
            key = p.get("cnpj") or "nome:" + (p.get("name") or "").upper()
            if not p.get("name") or key in seen:
                continue
            seen.add(key)
            c = Company(**{k: p.get(k) for k in COMPANY_FIELDS if k in p})
            c.registry_updated_at = parse_iso(p.get("registry_updated_at"))
            c.created_at = parse_iso(p.get("created_at")) or c.registry_updated_at or datetime.now(timezone.utc)
            db.add(c)
        db.commit()
    return len(seen)


def company_id_for(key: str | None):
    from app.db.database import SessionLocal
    from app.db.models import Company
    if not key:
        return None
    with SessionLocal() as db:
        if key.startswith("nome:"):
            c = db.query(Company).filter(Company.name == key[5:]).first() or \
                db.query(Company).filter(Company.name.ilike(key[5:])).first()
        else:
            c = db.query(Company).filter(Company.cnpj == key).first()
        return c.id if c else None


def replay(client, events: list[dict]) -> tuple[list, list]:
    """Reaplica as ações do CRM pela API, com a hora original de cada uma."""
    from app.db.database import SessionLocal
    from app.db.models import Suppression, Task
    from app.services.crm import clock
    applied, failed = [], []

    def ok(r, accept=()):
        return r.status_code < 300 or r.status_code in accept

    def detail(r):
        try:
            return str(r.json().get("detail"))[:200]
        except Exception:
            return f"HTTP {r.status_code}"

    for ev in events:
        tipo, dados, chave = ev["tipo"], ev.get("dados") or {}, ev.get("chave")
        at = parse_iso(ev.get("em")) or datetime.now(timezone.utc)
        why = None
        with clock(at):
            if tipo == "config":
                r = client.put("/api/settings", json=dados); why = None if ok(r) else detail(r)
            elif tipo == "empresa_criada":
                r = client.post("/api/companies", json=dados); why = None if ok(r, (409,)) else detail(r)
            elif tipo == "supressao" and not company_id_for(chave):
                cnpj = dados.get("cnpj") or (chave if chave and not chave.startswith("nome:") else None)
                if cnpj:
                    r = client.post("/api/suppression", json={"cnpj": cnpj, "reason": dados.get("reason", "")})
                    why = None if ok(r, (409,)) else detail(r)
                else:
                    why = "empresa não encontrada e sem CNPJ"
            elif tipo == "supressao_removida":
                cid = company_id_for(chave)
                with SessionLocal() as db:
                    q = db.query(Suppression)
                    s = (q.filter(Suppression.company_id == cid).first() if cid else None) or \
                        (q.filter(Suppression.cnpj == (dados.get("cnpj") or chave)).first())
                    sid = s.id if s else None
                if sid:
                    r = client.delete(f"/api/suppression/{sid}"); why = None if ok(r) else detail(r)
            else:
                cid = company_id_for(chave)
                if not cid:
                    why = "empresa não encontrada nesta atualização"
                elif tipo == "empresa_atualizada":
                    r = client.patch(f"/api/companies/{cid}", json=dados); why = None if ok(r) else detail(r)
                elif tipo == "interacao":
                    body = {**dados, "confirm_repeat": True, "happened_at": dados.get("happened_at") or at.isoformat()}
                    r = client.post(f"/api/companies/{cid}/interactions", json=body); why = None if ok(r) else detail(r)
                elif tipo == "tarefa":
                    r = client.post(f"/api/companies/{cid}/tasks", json=dados); why = None if ok(r) else detail(r)
                elif tipo == "tarefa_concluida":
                    with SessionLocal() as db:
                        t = (db.query(Task).filter(Task.company_id == cid, Task.title == dados.get("title"), Task.done.is_(False))
                             .order_by(Task.id).first())
                        tid = t.id if t else None
                    if tid:
                        r = client.patch(f"/api/tasks/{tid}", json={"done": True}); why = None if ok(r) else detail(r)
                elif tipo == "supressao":
                    r = client.post("/api/suppression", json={"company_id": cid, "reason": dados.get("reason", "")})
                    why = None if ok(r, (409,)) else detail(r)
                else:
                    why = f"tipo desconhecido: {tipo}"
        (failed if why else applied).append({"id": ev.get("id"), "tipo": tipo, "chave": chave, **({"motivo": why} if why else {})})
    return applied, failed


def crm_views(c) -> dict:
    """Respostas da API que a página publicada lê (central, inteligência, busca, fichas, CRM)."""
    g = lambda p: c.get("/api" + p).json()
    companies, page = [], 1
    while True:
        r = g(f"/companies/search?sort=score&per_page=100&page={page}&include_competitors=true&include_suppressed=true")
        companies += r["items"]
        if page * 100 >= r["total"] or not r["items"]:
            break
        page += 1
    fichas = {str(s["id"]): g(f"/companies/{s['id']}") for s in companies[:FICHAS_MAX]}
    approaches = {}   # abordagens prontas para as mais bem pontuadas (as demais aparecem na versão instalada)
    for sid in [str(s["id"]) for s in companies[:APPROACHES_MAX]]:
        r = c.get(f"/api/companies/{sid}/approach")
        if r.status_code == 200:
            approaches[sid] = r.json()
    return {
        "/command-center": g("/command-center"), "/daily-intelligence?limit=5": g("/daily-intelligence?limit=5"),
        "/pipeline": g("/pipeline"), "/tasks?status=open": g("/tasks?status=open"), "/settings": g("/settings"),
        "/suppression": g("/suppression"), "/regions": g("/regions"), "/debt-types": g("/debt-types"),
        "companies_all": companies, "fichas": fichas, "approaches": approaches,
        "/contacts": g("/contacts?limit=500"), "/scripts": g("/scripts"),
    }


def keep_companies() -> list[dict]:
    """Empresas que a próxima rodada recarrega (base da Receita e empresas captadas antes), com a data em
    que entraram na base. As cadastradas à mão e as de oportunidades manuais voltam pela reaplicação."""
    from app.db.database import SessionLocal
    from app.db.models import Company
    with SessionLocal() as db:
        out = []
        for c in db.query(Company).order_by(Company.id):
            if c.registry_source == "Cadastro manual" or (not c.cnpj and not c.opportunities and not c.pipeline_stage and not c.interactions):
                continue
            if c.opportunities and all(o.source_key and o.source_key.startswith("manual:") for o in c.opportunities) and not c.registry_source:
                continue
            d = {k: getattr(c, k) for k in COMPANY_FIELDS}
            d["id"] = c.id
            d["registry_updated_at"] = c.registry_updated_at.isoformat() if c.registry_updated_at else None
            d["created_at"] = c.created_at.isoformat() if c.created_at else None
            out.append(d)
        return out


def carry_first_seen(prev: dict):
    """'Captada em' = primeira vez que o registro apareceu (não a hora desta rodada)."""
    from app.db.database import SessionLocal
    from app.db.models import Opportunity
    first = {o["source_key"]: parse_iso(o.get("collected_at")) for o in prev.get("/opportunities", []) if o.get("source_key")}
    with SessionLocal() as db:
        for o in db.query(Opportunity).filter(Opportunity.source_key.in_(list(first) or ["-"])):
            if first[o.source_key] and first[o.source_key] < (o.collected_at if o.collected_at.tzinfo else o.collected_at.replace(tzinfo=timezone.utc)):
                o.collected_at = first[o.source_key]
        db.commit()


def replay_manual(client, manual: list[dict]) -> list[str]:
    """Oportunidades cadastradas na página publicada viram sinais reais no banco (com a evidência informada)."""
    from app.db.database import SessionLocal
    from app.db.models import Opportunity
    done = []
    fields = ["company_name", "cnpj", "segment", "city", "state", "kind", "title", "description", "evidence", "source_name", "source_url"]
    for m in sorted(manual, key=lambda m: m.get("criadoEm") or ""):
        body = {k: m.get(k) for k in fields if m.get(k) not in (None, "")}
        body.setdefault("source_name", "Cadastro manual")
        r = client.post("/api/opportunities", json=body)
        if r.status_code >= 300:
            continue
        with SessionLocal() as db:
            o = db.get(Opportunity, r.json()["id"])
            o.source_key = ("manual:" + str(m["_doc"]))[:180]
            o.collected_at = parse_iso(m.get("criadoEm")) or o.collected_at
            db.commit()
        done.append(m["_doc"])
    return done


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--previous")
    ap.add_argument("--uf", default="AM", help="UFs do mapa DataJud, separadas por vírgula (no máximo 6 por rodada)")
    ap.add_argument("--trigger", help="id da tarefa agendada que os botões de busca da página disparam")
    ap.add_argument("--crm", help="ações gravadas na página: pasta exportada do banco da página (crm_eventos/ e "
                                  "oportunidades_manuais/, um JSON por documento) ou um JSON único")
    ap.add_argument("--offline", action="store_true", help="não consulta fontes externas (teste local)")
    ap.add_argument("--seed-db", help="banco SQLite com empresas importadas da Receita para incluir na página")
    ap.add_argument("--seed-json", nargs="*", help="bases exportadas (bases/<UF>.json do ramo dados-cnpj)")
    a = ap.parse_args(argv)

    os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/snapshot.db"
    sys.path.insert(0, str(ROOT / "backend"))
    from fastapi.testclient import TestClient
    from app.main import app

    prev = previous_data(a.previous)
    events, manual = load_crm(a.crm)
    status = {}
    with TestClient(app) as c:
        seeded = seed_companies(prev, rows_from_db(a.seed_db) + rows_from_json(a.seed_json))
        if not a.offline:
            for name, path in [("PNCP", "/api/capture/pncp?mode=busca&max_pages=1"), ("Vagas", "/api/capture/jobs")]:
                r = c.post(path)
                status[name] = "ok" if r.status_code == 200 else f"falhou ({r.status_code})"
        ufs = list(dict.fromkeys(u.strip().upper() for u in a.uf.split(",") if u.strip()))[:6]
        market = {}
        for uf in ([] if a.offline else ufs):
            r = c.post(f"/api/market/datajud?uf={uf}")
            if r.status_code == 200:
                market[uf] = r.json()
            elif f"/market/datajud?uf={uf}" in prev:
                market[uf] = prev[f"/market/datajud?uf={uf}"]  # mantém a fotografia anterior
            status[f"DataJud {uf}"] = "ok" if r.status_code == 200 else f"falhou ({r.status_code}); mantida a anterior"
        for k, v in prev.items():  # mapas de outras UFs (e desta, se a consulta falhou) continuam até a próxima
            if k.startswith("/market/datajud?uf=") and k.split("=")[1] not in market:
                market[k.split("=")[1]] = v
        from app.db.database import SessionLocal
        from app.db.models import MarketSnapshot
        with SessionLocal() as db:   # contexto regional das fichas usa a fotografia mais recente de cada UF
            have = {m.uf for m in db.query(MarketSnapshot).all()}
            for uf, m in market.items():
                if uf not in have:
                    payload = {k: v for k, v in m.items() if k not in ("snapshot_id", "created_at")}
                    db.add(MarketSnapshot(source="datajud", uf=uf, period_start=m["periodo"]["inicio"], period_end=m["periodo"]["fim"],
                                          payload=payload, created_at=parse_iso(m.get("created_at")) or datetime.now(timezone.utc)))
            db.commit()
        carry_first_seen(prev)
        manual_done = replay_manual(c, manual)
        applied, failed = replay(c, events)
        c.post("/api/contacts/sync")   # só canais institucionais já presentes nas fichas
        g = lambda p: c.get("/api" + p).json()
        data = {
            "/dashboard/summary": g("/dashboard/summary"),
            "/opportunities": [o for o in g("/opportunities") if o["source_name"] != "Demonstração"],
            "/segments": g("/segments"), "/sources": g("/sources"), "/capture/runs": g("/capture/runs"),
            **crm_views(c),
        }
        for uf, m in market.items():
            data[f"/market/datajud?uf={uf}"] = m
        data["prospects_all"] = keep_companies()
    s, ops = data["/dashboard/summary"], data["/opportunities"]
    s.update(total=len(ops), hiring=sum(o["kind"] == "hiring" for o in ops), outsourcing=sum(o["kind"] == "outsourcing" for o in ops),
             public_procurement=sum(o["kind"] == "public_procurement" for o in ops),
             proven=sum(o.get("commercial_signal") == "oportunidade_comprovada" for o in ops),
             to_confirm=sum(o["kind"] == "public_procurement" and o.get("commercial_signal") == "sinal_a_confirmar" for o in ops))
    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-4)))
    all_ufs = sorted(k.split("=")[1] for k in data if k.startswith("/market/datajud?uf="))
    data["__meta"] = {"atualizado": now.strftime("%d/%m/%Y %H:%M") + " (Manaus)", "gerado_em": now.isoformat(), "status": status,
                      "ufs": [u for u in ufs if u in all_ufs] + [u for u in all_ufs if u not in ufs], "trigger_id": a.trigger,
                      "crm_aplicados": [e["id"] for e in applied if e.get("id")], "crm_falhas": failed,
                      "manuais_aplicados": manual_done, "empresas_carregadas": seeded}
    Path(a.out).write_text(render(data), encoding="utf-8")
    print(json.dumps({k: v for k, v in data["__meta"].items() if k != "crm_aplicados"} | {"crm_aplicados": len(applied)}, ensure_ascii=False))


def render(data: dict) -> str:
    fe = ROOT / "frontend"
    html, css, js = (fe / "index.html").read_text(), (fe / "styles.css").read_text(), (fe / "app.js").read_text()
    body = html[html.index("<body>") + 6:html.index("</body>")].replace('<script src="/static/app.js"></script>', "")
    fonts = re.search(r'<link href="https://fonts.googleapis.com[^>]+>', html).group(0)
    i = js.index("async function api("); j = js.index("}", js.index("return r.json();", i)) + 1
    js = js[:i] + "async function api(path, opt = {}) { return LC.api(path, opt); }" + js[j:]
    js = RUNTIME_JS.read_text(encoding="utf-8") + "\n" + js
    ufs = data["__meta"]["ufs"] or ["AM"]
    js = js.replace("u === 'AM' ? 'selected' : ''", f"u === '{ufs[0]}' ? 'selected' : ''")
    meta = data["__meta"]
    falhas = "; ".join(f"{k}: {v}" for k, v in meta["status"].items() if v != "ok")
    banner = (f"<b>Atualizado em {meta['atualizado']}</b> com dados reais (PNCP, vagas Greenhouse/Lever, DataJud; "
              f"empresas da última importação da Receita). Atualiza sozinha de hora em hora (aos 10 minutos)."
              + (f" <b>Falhas nesta rodada:</b> {falhas}." if falhas else "")
              + ' <span id="lc-pending"></span>')
    return f"""<title>LeadCob AI</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
{fonts}
<style>
:root{{color-scheme:dark}}
{css}
.demo-banner{{background:#21152f;border-bottom:1px solid #52316f;color:#e6d9f7;font:13px 'DM Sans',sans-serif;padding:9px max(16px,env(safe-area-inset-right,0px)) 9px max(16px,env(safe-area-inset-left,0px));text-align:center}}
.demo-banner b{{color:#fff}}
</style>
<div class="demo-banner">{banner}</div>
{body}
<script>window.__DEMO = {json.dumps(data, ensure_ascii=False).replace("</", "<\\/")};</script>
<script>
{js}
</script>
"""


RUNTIME_JS = Path(__file__).with_name("snapshot_runtime.js")

if __name__ == "__main__":
    main()
