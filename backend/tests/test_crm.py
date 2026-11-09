"""v0.5 — CRM, pontuação explicável, central de comando e inteligência do dia."""
import itertools
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import Company, Opportunity
from app.main import app
from app.services.cnpj import _dv, WEIGHTS_1, WEIGHTS_2
from app.services.lead_score import band, score_company

_seq = itertools.count(1)


def new_cnpj() -> str:
    base = f"{77000000 + next(_seq):08d}0001"
    d1 = _dv(base, WEIGHTS_1)
    return base + d1 + _dv(base + d1, WEIGHTS_2)


def make_company(**kw) -> int:
    defaults = dict(name=f"TESTE CRM {next(_seq)} LTDA", cnpj=new_cnpj(), state="AM", city="MANAUS", cnae_main="4639701",
                    target_profile="atacado", company_size="DEMAIS", capital_social=2_000_000.0,
                    registration_status="ATIVA", opened_at="2010-05-01", registry_source="teste")
    defaults.update(kw)
    with SessionLocal() as db:
        c = Company(**defaults)
        db.add(c); db.commit()
        return c.id


def add_signal(company_id, **kw):
    data = dict(company_id=company_id, kind="hiring", title="Analista de cobrança", source_name="Greenhouse",
                source_url="https://example.org/vaga", opportunity_class="operacao_interna", status="review",
                collected_at=datetime.now(timezone.utc))
    data.update(kw)
    with SessionLocal() as db:
        db.add(Opportunity(**data)); db.commit()


# ------------------------------------------------------------- pontuação (unidade)
def fake(**kw):
    base = dict(opportunities=[], interactions=[], cnae_main="4639701", target_profile="atacado", company_size=None,
                capital_social=None, state="AM", website=None, institutional_email=None, registration_status="ATIVA",
                segment=None, pipeline_stage=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_bands_follow_spec():
    assert band(100)[0] == band(80)[0] == "alta"
    assert band(79)[0] == band(60)[0] == "intermediaria"
    assert band(59)[0] == band(40)[0] == "pesquisar"
    assert band(39)[0] == band(0)[0] == "baixa"


def test_score_components_are_explained_and_sum_to_total():
    sig = SimpleNamespace(kind="hiring", opportunity_class="operacao_interna", commercial_signal=None, evidence="x",
                          status="review", collected_at=datetime.now(timezone.utc))
    r = score_company(fake(opportunities=[sig], company_size="DEMAIS", capital_social=5e6, website="https://x"), {"ufs_atuacao": ["AM"]})
    assert r["score"] == sum(p["points"] for p in r["components"])
    assert all(p["nature"] in ("fato", "indício", "hipótese") and p["reason"] for p in r["components"])
    assert {p["key"] for p in r["components"]} >= {"aderencia", "evidencia", "atualidade", "potencial", "geografia", "canal"}
    assert r["band"] == "alta" and "não probabilidade" in r["disclaimer"]
    # sem sinal o mesmo cadastro cai bastante: o sinal é fato, o setor é hipótese
    assert score_company(fake(company_size="DEMAIS", capital_social=5e6), {"ufs_atuacao": ["AM"]})["score"] < r["score"] - 30


def test_competitor_inactive_and_suppressed_score_zero():
    assert score_company(fake(cnae_main="8291100"), {})["band"] == "concorrente"
    inactive = score_company(fake(registration_status="BAIXADA"), {})
    assert inactive["score"] == 0 and inactive["band"] == "inativa"
    sup = score_company(fake(), {}, suppressed=True)
    assert sup["score"] == 0 and sup["band"] == "nao_contatar"


def test_geography_outside_configured_ufs_scores_zero():
    comp = {p["key"]: p for p in score_company(fake(state="SP"), {"ufs_atuacao": ["AM"]})["components"]}
    assert comp["geografia"]["points"] == 0


# ------------------------------------------------------------- API do CRM
def test_manual_company_validates_and_deduplicates_cnpj():
    cnpj = new_cnpj()
    with TestClient(app) as c:
        assert c.post("/api/companies", json={"name": "X", "cnpj": "11.111.111/0001-00"}).status_code in (400, 422)
        r = c.post("/api/companies", json={"name": "EMPRESA MANUAL LTDA", "cnpj": cnpj, "state": "am", "cnae_main": "8511200"})
        assert r.status_code == 201
        body = r.json()
        assert body["stage"] == "identificada" and body["state"] == "AM" and body["profile"]
        assert body["timeline"][0]["summary"] == "Empresa cadastrada manualmente"
        dup = c.post("/api/companies", json={"name": "OUTRA", "cnpj": cnpj})
        assert dup.status_code == 409 and f"id {body['id']}" in dup.json()["detail"]
        assert c.post("/api/companies", json={"name": "empresa manual ltda"}).status_code == 409   # sem CNPJ: pelo nome


def test_interactions_advance_stage_and_block_repeated_outreach():
    cid = make_company()
    with TestClient(app) as c:
        r = c.post(f"/api/companies/{cid}/interactions",
                   json={"kind": "contato", "channel": "email", "summary": "Primeiro e-mail ao financeiro", "follow_up_days": 3})
        assert r.status_code == 201 and r.json()["stage"] == "primeiro_contato"
        again = c.post(f"/api/companies/{cid}/interactions", json={"kind": "follow_up", "summary": "Reforço"})
        assert again.status_code == 409 and "menos de 7 dias" in again.json()["detail"]
        ok = c.post(f"/api/companies/{cid}/interactions", json={"kind": "follow_up", "summary": "Reforço", "confirm_repeat": True})
        assert ok.json()["stage"] == "aguardando_resposta"
        # resposta não é abordagem: não sofre a trava e avança o funil
        assert c.post(f"/api/companies/{cid}/interactions", json={"kind": "resposta", "summary": "Pediram proposta"}).json()["stage"] == "em_negociacao"
        # registrar etapa anterior não faz o funil voltar
        assert c.post(f"/api/companies/{cid}/interactions", json={"kind": "nota", "summary": "obs"}).json()["stage"] == "em_negociacao"
        assert c.post(f"/api/companies/{cid}/interactions", json={"kind": "etapa", "summary": "teste"}).status_code == 400
        assert c.post(f"/api/companies/{cid}/interactions", json={"kind": "contato", "channel": "pombo", "summary": "teste"}).status_code == 400
        sheet = c.get(f"/api/companies/{cid}").json()
        kinds = [t["kind"] for t in sheet["timeline"]]
        assert kinds.count("etapa") == 3 and "contato" in kinds and "resposta" in kinds
        assert sheet["tasks"] and sheet["tasks"][0]["title"].startswith("Follow-up")
        assert sheet["last_outreach_at"]
        assert any(t["company_id"] == cid for t in c.get("/api/tasks").json())


def test_lost_requires_reason_and_lowers_score():
    cid = make_company()
    with TestClient(app) as c:
        before = c.get(f"/api/companies/{cid}").json()["score"]
        assert c.patch(f"/api/companies/{cid}", json={"stage": "perdido"}).status_code == 400
        r = c.patch(f"/api/companies/{cid}", json={"stage": "perdido", "lost_reason": "Já tem assessoria contratada"}).json()
        assert r["stage"] == "perdido" and r["lost_reason"] == "Já tem assessoria contratada"
        assert r["score"] == before - 20
        assert "Já tem assessoria contratada" in r["timeline"][0]["summary"]
        assert c.patch(f"/api/companies/{cid}", json={"stage": "inexistente"}).status_code == 400


def test_next_action_and_potential_value_are_logged():
    cid = make_company()
    when = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with TestClient(app) as c:
        r = c.patch(f"/api/companies/{cid}", json={"next_action": "Ligar para o financeiro", "next_action_at": when,
                                                    "potential_value": 12500.5}).json()
        assert r["next_action"] == "Ligar para o financeiro" and r["potential_value"] == 12500.5
        summaries = " | ".join(t["summary"] for t in r["timeline"])
        assert "R$ 12.500,50" in summaries and "Ligar para o financeiro" in summaries
        cc = c.get("/api/command-center").json()
        assert any(x["company_id"] == cid and x["kind"] == "proxima_atividade" for x in cc["followups_atrasados"])


def test_suppression_blocks_contact_search_export_and_intelligence():
    cid = make_company(name="SUPRIMIDA TESTE LTDA")
    add_signal(cid)
    with TestClient(app) as c:
        cnpj = c.get(f"/api/companies/{cid}").json()["cnpj"]
        r = c.post("/api/suppression", json={"company_id": cid, "reason": "Pediu para não receber contato"})
        assert r.status_code == 201
        assert c.post("/api/suppression", json={"cnpj": cnpj}).status_code == 409
        sheet = c.get(f"/api/companies/{cid}").json()
        assert sheet["stage"] == "nao_contatar" and sheet["suppressed"] and sheet["score"] == 0
        assert "supressão" in sheet["blocked_reason"] or "Não contatar" in sheet["blocked_reason"]
        assert c.post(f"/api/companies/{cid}/interactions", json={"kind": "contato", "summary": "teste"}).status_code == 409
        assert c.patch(f"/api/companies/{cid}", json={"stage": "qualificada"}).status_code == 409
        assert c.get("/api/companies/search", params={"q": "SUPRIMIDA TESTE"}).json()["items"] == []
        incl = c.get("/api/companies/search", params={"q": "SUPRIMIDA TESTE", "include_suppressed": True}).json()["items"]
        assert [i["id"] for i in incl] == [cid]
        assert cnpj[:8] not in c.get("/api/export/companies.csv").text.replace(".", "")
        assert cid not in [i["id"] for i in c.get("/api/daily-intelligence", params={"limit": 20}).json()["itens"]]
        sup_id = next(s["id"] for s in c.get("/api/suppression").json() if s["company_id"] == cid)
        assert c.delete(f"/api/suppression/{sup_id}").json()["ok"]
        assert c.get(f"/api/companies/{cid}").json()["stage"] == "acompanhar_futuramente"
        # marcar 'Não contatar' pelo funil também cria a supressão
        assert c.patch(f"/api/companies/{cid}", json={"stage": "nao_contatar", "stage_reason": "pedido"}).json()["suppressed"]


def test_settings_validate_ufs_and_change_geography_score():
    cid = make_company(state="RR")
    with TestClient(app) as c:
        assert c.put("/api/settings", json={"ufs_atuacao": ["XX"]}).status_code == 400
        assert c.put("/api/settings", json={"dias_entre_contatos": 0}).status_code == 422
        c.put("/api/settings", json={"ufs_atuacao": ["rr", "AM"]})
        geo = {p["key"]: p for p in c.get(f"/api/companies/{cid}").json()["score_detail"]["components"]}["geografia"]
        assert geo["points"] == 10
        c.put("/api/settings", json={"ufs_atuacao": []})
        assert c.get("/api/settings").json()["ufs_atuacao"] == []


def test_search_filters_and_pagination():
    tag = "FILTRO NACIONAL"
    a = make_company(name=f"{tag} A", state="RS", city="PORTO ALEGRE", cnae_main="4711302", target_profile="varejo",
                     capital_social=50_000.0, opened_at="2023-01-10")
    b = make_company(name=f"{tag} B", state="BA", city="SALVADOR", cnae_main="8630501", target_profile="saude_privada",
                     capital_social=900_000.0, opened_at="2001-01-10")
    make_company(name=f"{tag} C CONCORRENTE", state="SP", cnae_main="8291100", target_profile=None)
    add_signal(b)
    with TestClient(app) as c:
        ids = lambda **p: [i["id"] for i in c.get("/api/companies/search", params={"q": tag, **p}).json()["items"]]
        assert set(ids()) == {a, b}  # concorrente fora por padrão
        assert len(ids(include_competitors=True)) == 3
        assert ids(region="Sul") == [a] and ids(uf="BA,SE") == [b]
        assert ids(cnae="8630") == [b] and ids(municipio="porto") == [a]
        assert ids(years_min=10) == [b] and ids(years_max=5) == [a]
        assert ids(capital_min=100000) == [b] and ids(has_signal=True) == [b] and ids(has_signal=False) == [a]
        assert ids(sort="score")[0] == b  # sinal pesa mais que cadastro
        page = c.get("/api/companies/search", params={"q": tag, "per_page": 1, "page": 2, "sort": "name"}).json()
        assert page["total"] == 2 and [i["id"] for i in page["items"]] == [b]
        assert c.get("/api/companies/search", params={"region": "Marte"}).status_code == 400
        assert c.get("/api/regions").json()["Norte"][0] == "AC"


def test_command_center_and_daily_intelligence():
    hot = make_company(name="INTELIGENCIA DIA LTDA", website="https://exemplo.com.br")
    add_signal(hot)
    contacted = make_company(name="JA CONTATADA LTDA")
    add_signal(contacted)
    with TestClient(app) as c:
        c.post(f"/api/companies/{contacted}/interactions", json={"kind": "contato", "summary": "e-mail"})
        cc = c.get("/api/command-center").json()
        assert len(cc["pipeline"]) == 13 and cc["pipeline"][0]["key"] == "identificada"
        assert {"empresas_total", "leads_qualificados", "contatos_realizados", "taxa_conversao", "valor_potencial"} <= cc["kpis"].keys()
        assert cc["kpis"]["contatos_realizados"] >= 1 and cc["kpis"]["empresas_novas_hoje"] >= 2
        di = c.get("/api/daily-intelligence", params={"limit": 20}).json()
        got = {i["id"]: i for i in di["itens"]}
        assert contacted not in got  # contatada há menos de 7 dias
        item = got[hot]
        assert item["evidencia"]["natureza"] == "fato" and item["evidencia"]["url"]
        assert item["fatos"] and item["hipoteses"] and "inadimplência" in item["cuidado"]
        assert item["abertura"] and item["proxima_acao"] and item["canal"] == "site institucional"
        assert "sem modelo de linguagem" in di["metodo"]


def test_old_database_gets_crm_columns_and_tables():
    db = Path(tempfile.mkdtemp()) / "v04.db"
    con = sqlite3.connect(db)
    con.executescript("""
      CREATE TABLE companies (id INTEGER PRIMARY KEY, name VARCHAR(220), cnpj VARCHAR(14), segment VARCHAR(120),
        city VARCHAR(100), state VARCHAR(2), website VARCHAR(500), institutional_email VARCHAR(255), created_at TIMESTAMP);
      INSERT INTO companies (name, cnpj, state) VALUES ('ANTIGA LTDA', '11222333000181', 'AM');
    """)
    con.close()
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, "-c", "from app.db.database import ensure_schema; ensure_schema()"], cwd=root,
                   check=True, env={"DATABASE_URL": f"sqlite:///{db}", "PATH": ""})
    con = sqlite3.connect(db)
    cols = {r[1] for r in con.execute("PRAGMA table_info(companies)")}
    assert {"pipeline_stage", "next_action_at", "potential_value", "lost_reason", "notes"} <= cols
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"interactions", "tasks", "suppressions", "settings"} <= tables
    assert con.execute("SELECT name FROM companies").fetchone()[0] == "ANTIGA LTDA"


def test_fictitious_demo_rows_are_removed_unless_requested():
    from app.main import remove_demo
    with SessionLocal() as db:
        c = Company(name="EXEMPLO FICTICIO")
        db.add(c); db.flush()
        db.add(Opportunity(company_id=c.id, kind="hiring", title="exemplo", source_name="Demonstração"))
        db.commit()
        assert remove_demo(db) == 1
        assert db.query(Company).filter_by(name="EXEMPLO FICTICIO").count() == 0
        assert db.query(Opportunity).filter_by(source_name="Demonstração").count() == 0
