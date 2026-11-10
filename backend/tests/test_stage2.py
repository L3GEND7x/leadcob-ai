"""v0.5.2 — gerador de abordagens, carteira (faixas de atraso), laboratório de negociação e scripts."""
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal, ensure_schema
from app.db.models import Company, Opportunity
from app.main import app
from app.services import collection, negotiation
from tests.test_crm import make_company

ensure_schema()


# ------------------------------------------------------------- abordagens
def test_approach_uses_facts_and_never_claims_delinquency():
    cid = make_company(name="ABORDAGEM VAGA LTDA")
    with SessionLocal() as db:
        db.add(Opportunity(company_id=cid, kind="hiring", title="Analista de Cobrança Pleno", source_name="Greenhouse",
                           source_url="https://example.org/v", opportunity_class="operacao_interna", status="review",
                           collected_at=datetime.now(timezone.utc)))
        db.commit()
    with TestClient(app) as c:
        a = c.get(f"/api/companies/{cid}/approach").json()
        assert a["modo"] == "comercial" and len(a["mensagens"]) == 3 and len(a["follow_ups"]) == 7
        email = a["mensagens"][0]
        assert "Analista de Cobrança Pleno" in email["texto"] and "[PREENCHER]" in email["texto"]
        assert "não receber novos contatos" in email["texto"]   # opt-out sempre presente
        texts = " ".join([m.get("texto", "") for m in a["mensagens"]] + [f["texto"] for f in a["follow_ups"]]).lower()
        for forbidden in ("vocês têm inadimpl", "seus inadimplentes", "sua inadimplência", "estão inadimplentes"):
            assert forbidden not in texts
        assert any("Hipótese" in b for b in a["baseado_em"])
        c.put("/api/settings", json={"remetente_nome": "Ana Teste", "remetente_empresa": "Escritório Teste"})
        assert "Ana Teste" in c.get(f"/api/companies/{cid}/approach").json()["mensagens"][0]["texto"]
        c.put("/api/settings", json={"remetente_nome": "", "remetente_empresa": ""})


def test_approach_blocked_for_suppressed_and_edital_mode():
    sup = make_company(name="ABORDAGEM SUPRIMIDA LTDA")
    pub = make_company(name="ORGAO ABORDAGEM", cnae_main=None, target_profile=None, segment="Órgão público")
    with SessionLocal() as db:
        db.add(Opportunity(company_id=pub, kind="public_procurement", title="Credenciamento de cobrança", source_name="PNCP",
                           source_url="https://pncp.gov.br/x", opportunity_class="edital_aberto",
                           commercial_signal="oportunidade_comprovada", status="review", collected_at=datetime.now(timezone.utc)))
        db.commit()
    with TestClient(app) as c:
        c.post("/api/suppression", json={"company_id": sup, "reason": "opt-out"})
        assert c.get(f"/api/companies/{sup}/approach").status_code == 409
        a = c.get(f"/api/companies/{pub}/approach").json()
        assert a["modo"] == "edital" and a["mensagens"] == [] and "edital" in a["aviso"]


# ------------------------------------------------------------- carteira e faixas
CSV = """Título;Valor;Vencimento;Pagamento;CPF;Nome do devedor;Tipo devedor
NF-1;R$ 1.000,00;10/11/2026;;123.456.789-09;Fulano;PF
NF-2;500,50;05/11/2026;;;;PJ
NF-3;2000;2026-10-20;;;;PJ
NF-4;300;2026-09-20;;;;PJ
NF-5;400;2026-08-30;;;;PJ
NF-6;700;2026-06-01;;;;PJ
NF-7;900;2026-01-01;;;;PJ
NF-8;100;2026-01-01;2026-02-01;;;PJ
123.456.789-09;50;2026-11-20;;;;
NF-X;abc;2026-11-20;;;;
"""


def test_csv_import_drops_personal_columns_and_bands_are_right():
    parsed = collection.parse_csv(CSV)
    assert len(parsed["items"]) == 9 and parsed["errors"][0]["linha"] == 11
    assert set(parsed["personal_columns_dropped"]) == {"CPF", "Nome do devedor"}
    assert all("Fulano" not in str(i) and "123.456" not in str(i) for i in parsed["items"])   # nem nome nem CPF
    r = collection.analyze(parsed["items"], date(2026, 11, 10))
    by = {b["key"]: b for b in r["faixas"]}
    assert (by["a_vencer"]["titulos"], by["d1_7"]["titulos"], by["d8_30"]["titulos"], by["d31_60"]["titulos"],
            by["d61_90"]["titulos"], by["d91_180"]["titulos"], by["d180"]["titulos"]) == (2, 1, 1, 1, 1, 1, 1)
    assert by["a_vencer"]["valor"] == 1050.0 and by["d1_7"]["valor"] == 500.5
    assert r["resumo"]["titulos_pagos"] == 1 and r["resumo"]["titulos_pf_abertos"] == 1
    assert "NECESSÁRIO CONFERIR" in by["d91_180"]["estrategia"]


def test_portfolio_api_roundtrip():
    with TestClient(app) as c:
        r = c.post("/api/portfolios", json={"name": "Carteira teste", "csv": CSV, "reference_date": "2026-11-10", "accept_partial": True})
        assert r.status_code == 201
        body = r.json()
        assert body["resumo"]["valor_vencido"] == pytest.approx(500.5 + 2000 + 300 + 400 + 700 + 900)
        assert body["importacao"]["colunas_pessoais_descartadas"]
        assert any(p["id"] == body["id"] for p in c.get("/api/portfolios").json())
        later = c.get(f"/api/portfolios/{body['id']}", params={"reference_date": "2026-12-31"}).json()
        assert {b["key"]: b["titulos"] for b in later["faixas"]}["a_vencer"] == 0
        assert c.post("/api/portfolios", json={"name": "Carteira sem colunas", "csv": "coluna_a;coluna_b\n1;2\n"}).status_code == 400
        assert c.delete(f"/api/portfolios/{body['id']}").json()["ok"]


# ------------------------------------------------------------- negociação
def test_negotiation_uses_only_user_premises():
    base = {"valor_original": 1000, "vencimento": "2026-08-12", "data_base": "2026-11-10"}   # 90 dias
    zero = negotiation.simulate(base)
    assert zero["total_atualizado"] == 1000 and zero["juros"] == 0 and "Nenhum encargo" in zero["avisos"][0]
    r = negotiation.simulate({**base, "multa_pct": 2, "juros_mes_pct": 1, "correcao_pct": 1.5, "desconto_pct": 50,
                              "entrada": 100, "parcelas": 3})
    assert r["dias_atraso"] == 90 and r["correcao"] == 15 and r["multa"] == 20.3 and r["juros"] == 30.45
    assert r["valor_acordado"] == pytest.approx(1065.75 - 65.75 / 2, abs=0.01)
    assert r["valor_parcela"] == pytest.approx((r["valor_acordado"] - 100) / 3, abs=0.01)
    price = negotiation.simulate({**base, "parcelas": 12, "juros_parcelamento_mes_pct": 2})
    assert price["valor_parcela"] == pytest.approx(94.56, abs=0.01)
    with TestClient(app) as c:
        assert c.post("/api/negotiation/simulate", json={**base, "entrada": 5000}).status_code == 400
        assert c.post("/api/negotiation/simulate", json=base).json()["dias_atraso"] == 90


def test_scripts_library():
    with TestClient(app) as c:
        d = c.get("/api/scripts").json()
        assert len(d["scripts"]) >= 10 and "Objeções" in d["categorias"]
        assert all(s["texto"] for s in d["scripts"])
        assert c.get("/api/scripts", params={"categoria": "Follow-up"}).json()["scripts"][0]["categoria"] == "Follow-up"
