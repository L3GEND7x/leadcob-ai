"""Relatórios do período (issue #18): contagens do que está registrado, sem projeções."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db.database import ensure_schema
from app.main import app
from tests.test_crm import add_signal, make_company

ensure_schema()


def test_summary_counts_activity_conversion_losses_and_signals():
    a = make_company(name="RELATORIO A LTDA")
    b = make_company(name="RELATORIO B LTDA")
    add_signal(a, source_name="Fonte Relatório Teste")
    with TestClient(app) as c:
        before = c.get("/api/reports/summary", params={"dias": 7}).json()
        c.post(f"/api/companies/{a}/interactions", json={"kind": "contato", "summary": "e-mail enviado"})
        c.post(f"/api/companies/{a}/interactions", json={"kind": "resposta", "summary": "pediram proposta"})
        c.post(f"/api/companies/{b}/interactions", json={"kind": "contato", "summary": "ligação"})
        c.patch(f"/api/companies/{b}", json={"stage": "perdido", "lost_reason": "Já tem assessoria (relatório)"})
        r = c.get("/api/reports/summary", params={"dias": 7}).json()
        act = {x["tipo"]: x for x in r["atividade"]}
        old = {x["tipo"]: x for x in before["atividade"]}
        assert act["Contatos"]["registros"] - old["Contatos"]["registros"] == 2
        assert act["Respostas"]["registros"] - old["Respostas"]["registros"] == 1
        conv = {x["etapa"]: x for x in r["conversao"]}
        assert conv["Contatos"]["empresas"] >= 2 and conv["Respostas"]["empresas"] >= 1
        assert any(m["motivo"] == "Já tem assessoria (relatório)" for m in r["perdas"]["motivos"])
        assert any(x["key"] == "perdido" for x in r["funil_entradas"])
        assert any(f["fonte"] == "Fonte Relatório Teste" for f in r["sinais_novos"]["por_fonte"])
        assert r["periodo"]["dias"] == 7 and "projeções" in r["notas"][0]
        # período sem atividade
        old_period = c.get("/api/reports/summary", params={"inicio": "2020-01-01", "fim": "2020-01-31"}).json()
        assert old_period["empresas_contatadas"] == 0 and old_period["conversao"][0]["pct_contatadas"] is None
        assert c.get("/api/reports/summary", params={"inicio": "2026-02-01", "fim": "2026-01-01"}).status_code == 400
        csv = c.get("/api/reports/summary.csv", params={"dias": 7})
        assert csv.status_code == 200 and "atividade;Contatos" in csv.text
