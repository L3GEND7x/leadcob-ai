"""Página publicada: o script reaplica as ações do CRM gravadas na página, com a hora original."""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def build(tmp: Path, prev: dict, crm: dict) -> dict:
    prev_html = tmp / "prev.html"
    prev_html.write_text(f"<script>window.__DEMO = {json.dumps(prev)};</script>", encoding="utf-8")
    (tmp / "crm.json").write_text(json.dumps(crm), encoding="utf-8")
    out = tmp / "page.html"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_dashboard_snapshot.py"), "--out", str(out), "--previous", str(prev_html),
                    "--crm", str(tmp / "crm.json"), "--offline"], check=True, cwd=ROOT, capture_output=True)
    html = out.read_text(encoding="utf-8")
    assert "LC.api(path, opt)" in html and "window.claude" in html
    return json.loads(re.search(r"window\.__DEMO = (\{.*?\});</script>", html, re.S).group(1))


def test_published_page_replays_crm_actions():
    tmp = Path(tempfile.mkdtemp())
    prev = {"prospects_all": [{"name": "ATACADO TESTE LTDA", "cnpj": "92498138000180", "state": "AM", "city": "MANAUS",
                               "cnae_main": "4687701", "target_profile": "atacado", "registration_status": "ATIVA",
                               "company_size": "DEMAIS", "capital_social": 1500000.0, "registry_source": "Receita Federal — teste",
                               "created_at": "2026-11-01T10:00:00+00:00"}]}
    crm = {"eventos": [
        {"id": "a", "em": "2026-11-05T13:00:00Z", "tipo": "empresa_atualizada", "chave": "92498138000180", "dados": {"stage": "qualificada"}},
        {"id": "b", "em": "2026-11-05T14:00:00Z", "tipo": "interacao", "chave": "92498138000180",
         "dados": {"kind": "contato", "channel": "email", "summary": "Apresentação", "follow_up_days": 3}},
        {"id": "c", "em": "2026-11-06T09:00:00Z", "tipo": "interacao", "chave": "92498138000180", "dados": {"kind": "follow_up", "summary": "Reforço"}},
        {"id": "d", "em": "2026-11-06T10:00:00Z", "tipo": "empresa_criada", "chave": "nome:LOJA NOVA LTDA", "dados": {"name": "LOJA NOVA LTDA", "state": "AM"}},
        {"id": "e", "em": "2026-11-06T11:00:00Z", "tipo": "interacao", "chave": "nome:SEM CADASTRO", "dados": {"kind": "nota", "summary": "x y"}},
    ], "oportunidades_manuais": [{"_doc": "m1", "company_name": "LOJA NOVA LTDA", "kind": "hiring", "title": "Vaga de cobrança",
                                   "evidence": "Vista no site da loja", "criadoEm": "2026-11-06T12:00:00Z"}]}
    d = build(tmp, prev, crm)
    co = next(c for c in d["companies_all"] if c["cnpj"] == "92498138000180")
    assert co["stage"] == "aguardando_resposta"   # contato → primeiro contato; follow-up → aguardando resposta
    sheet = d["fichas"][str(co["id"])]
    times = [t["at"][:16] for t in sheet["timeline"] if t["kind"] == "etapa"]
    assert "2026-11-05T13:00" in times and "2026-11-06T09:00" in times   # hora original, não a da atualização
    assert sheet["tasks"][0]["due_at"].startswith("2026-11-08T14:00")
    assert sorted(d["__meta"]["crm_aplicados"]) == ["a", "b", "c", "d"]
    assert d["__meta"]["crm_falhas"][0]["id"] == "e" and d["__meta"]["manuais_aplicados"] == ["m1"]
    lojas = [c for c in d["companies_all"] if c["name"] == "LOJA NOVA LTDA"]
    assert len(lojas) == 1 and lojas[0]["signals"] == 1   # sem duplicar pelo nome
    # a próxima rodada recarrega a base da Receita, mas não as empresas manuais (voltam pela reaplicação)
    assert [p["cnpj"] for p in d["prospects_all"]] == ["92498138000180"]
    assert d["prospects_all"][0]["created_at"].startswith("2026-11-01")
    assert {"/command-center", "/daily-intelligence?limit=5", "/pipeline", "/settings", "/regions", "/debt-types"} <= d.keys()


def test_crm_actions_can_come_from_page_database_export():
    """A tarefa horária exporta o banco da página como <pasta>/<coleção>/<doc_id>.json."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_dashboard_snapshot import load_crm
    tmp = Path(tempfile.mkdtemp())
    (tmp / "crm_eventos").mkdir(); (tmp / "oportunidades_manuais").mkdir()
    (tmp / "crm_eventos" / "zz9.json").write_text(json.dumps({"tipo": "config", "em": "2026-11-09T10:00:00Z", "dados": {}}))
    (tmp / "crm_eventos" / "aa1.json").write_text(json.dumps({"tipo": "tarefa", "em": "2026-11-09T11:00:00Z", "chave": "x", "dados": {}}))
    (tmp / "oportunidades_manuais" / "m7.json").write_text(json.dumps({"company_name": "X", "criadoEm": "2026-11-09T09:00:00Z"}))
    events, manual = load_crm(str(tmp))
    assert [e["id"] for e in events] == ["zz9", "aa1"]   # ordem pela hora da ação
    assert manual[0]["_doc"] == "m7"


def test_seed_db_brings_registry_companies():
    import sqlite3
    tmp = Path(tempfile.mkdtemp())
    db = tmp / "am.db"
    con = sqlite3.connect(db)
    con.executescript("""CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT, cnpj TEXT, state TEXT, cnae_main TEXT,
      target_profile TEXT, registration_status TEXT, registry_source TEXT, created_at TEXT);
      INSERT INTO companies VALUES (1, 'DISTRIBUIDORA AM LTDA', '11222333000181', 'AM', '4639701', 'atacado', 'ATIVA',
      'Receita Federal — teste', '2026-11-10T10:00:00+00:00');""")
    con.close()
    prev_html = tmp / "prev.html"; prev_html.write_text("<script>window.__DEMO = {};</script>", encoding="utf-8")
    out = tmp / "page.html"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_dashboard_snapshot.py"), "--out", str(out), "--previous", str(prev_html),
                    "--seed-db", str(db), "--offline"], check=True, cwd=ROOT, capture_output=True)
    d = json.loads(re.search(r"window\.__DEMO = (\{.*?\});</script>", out.read_text(encoding="utf-8"), re.S).group(1))
    assert [c["name"] for c in d["companies_all"]] == ["DISTRIBUIDORA AM LTDA"]
    assert d["prospects_all"][0]["cnpj"] == "11222333000181"   # continua nas próximas rodadas
