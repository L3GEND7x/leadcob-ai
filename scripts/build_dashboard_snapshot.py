"""Gera a página estática do painel (dados reais) para publicação privada.

Uso (na raiz do repositório):
    python scripts/build_dashboard_snapshot.py --out painel.html [--previous pagina_anterior.html] [--uf AM,PA]

Passos: cria um banco temporário, roda as captações ao vivo (PNCP, vagas
Greenhouse/Lever, DataJud por UF), lê os dados pela própria API e embute tudo
num HTML único com o frontend do projeto. Empresas-alvo (base CNPJ) vêm da
página anterior (--previous), porque a importação da Receita é um job mensal
lento. Falha de uma fonte não derruba as outras: o erro vai para o rodapé.
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


def previous_data(path: str | None) -> dict:
    if not path or not Path(path).exists():
        return {}
    m = re.search(r"window\.__DEMO = (\{.*?\});</script>", Path(path).read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1)) if m else {}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--previous")
    ap.add_argument("--uf", default="AM", help="UFs do mapa DataJud, separadas por vírgula (no máximo 6 por rodada)")
    ap.add_argument("--trigger", help="id da tarefa agendada que os botões de busca da página disparam")
    a = ap.parse_args(argv)

    os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/snapshot.db"
    sys.path.insert(0, str(ROOT / "backend"))
    from fastapi.testclient import TestClient
    from app.main import app

    prev = previous_data(a.previous)
    status = {}
    with TestClient(app) as c:
        for name, path in [("PNCP", "/api/capture/pncp?mode=busca&max_pages=1"), ("Vagas", "/api/capture/jobs")]:
            r = c.post(path)
            status[name] = "ok" if r.status_code == 200 else f"falhou ({r.status_code})"
        ufs = list(dict.fromkeys(u.strip().upper() for u in a.uf.split(",") if u.strip()))[:6]
        market = {}
        for uf in ufs:
            r = c.post(f"/api/market/datajud?uf={uf}")
            if r.status_code == 200:
                market[uf] = r.json()
            elif f"/market/datajud?uf={uf}" in prev:
                market[uf] = prev[f"/market/datajud?uf={uf}"]  # mantém a fotografia anterior
            status[f"DataJud {uf}"] = "ok" if r.status_code == 200 else f"falhou ({r.status_code}); mantida a anterior"
        g = lambda p: c.get("/api" + p).json()
        data = {
            "/dashboard/summary": g("/dashboard/summary"),
            "/opportunities": [o for o in g("/opportunities") if o["source_name"] != "Demonstração"],
            "/segments": g("/segments"), "/sources": g("/sources"), "/capture/runs": g("/capture/runs"),
            "prospects_all": prev.get("prospects_all", []),
        }
        for k, v in prev.items():  # mapas de outras UFs continuam até a próxima atualização delas
            if k.startswith("/market/datajud?uf="):
                data[k] = v
        for uf, m in market.items():
            data[f"/market/datajud?uf={uf}"] = m
    # contadores coerentes com o que a página mostra
    s, ops = data["/dashboard/summary"], data["/opportunities"]
    s.update(total=len(ops), hiring=sum(o["kind"] == "hiring" for o in ops), outsourcing=sum(o["kind"] == "outsourcing" for o in ops),
             public_procurement=sum(o["kind"] == "public_procurement" for o in ops), prospects=len(data["prospects_all"]),
             proven=sum(o.get("commercial_signal") == "oportunidade_comprovada" for o in ops),
             to_confirm=sum(o["kind"] == "public_procurement" and o.get("commercial_signal") == "sinal_a_confirmar" for o in ops))
    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-4)))
    all_ufs = sorted(k.split("=")[1] for k in data if k.startswith("/market/datajud?uf="))
    data["__meta"] = {"atualizado": now.strftime("%d/%m/%Y %H:%M") + " (Manaus)", "status": status,
                      "ufs": list(market) + [u for u in all_ufs if u not in market], "trigger_id": a.trigger}
    Path(a.out).write_text(render(data), encoding="utf-8")
    print(json.dumps(data["__meta"], ensure_ascii=False))


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
              f"empresas-alvo da última importação da Receita). Atualiza sozinha de hora em hora (aos 10 minutos); os botões de busca pedem uma atualização na hora (3 a 6 minutos)."
              + (f" <b>Falhas nesta rodada:</b> {falhas}." if falhas else ""))
    return f"""<title>LeadCob AI</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
{fonts}
<style>
:root{{color-scheme:dark}}
{css}
.demo-banner{{background:#2a1218;border-bottom:1px solid #5b202c;color:#f3d6db;font:13px 'DM Sans',sans-serif;padding:10px max(16px,env(safe-area-inset-right,0px)) 10px max(16px,env(safe-area-inset-left,0px));text-align:center}}
.demo-banner b{{color:#fff}}
</style>
<div class="demo-banner">{banner}</div>
{body}
<script>window.__DEMO = {json.dumps(data, ensure_ascii=False)};</script>
<script>
{js}
</script>
"""


RUNTIME_JS = Path(__file__).with_name("snapshot_runtime.js")

if __name__ == "__main__":
    main()
