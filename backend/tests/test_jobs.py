"""Vagas: classificação pelo título (casos reais de 09/11/2026) e conector com transporte simulado."""
import json

import httpx
import pytest

from app.collectors import jobboards
from app.services.jobs import classify_job, score_job, strip_html


@pytest.mark.parametrize("title,expected,role", [
    ("Especialista de Políticas de Recuperação de Crédito | Consignado", "alta", "estrategia_dados"),
    ("DATA SCIENCE COORDINATOR | CREDIT & COLLECTIONS", "alta", "estrategia_dados"),
    ("Business Analyst Júnior - Collections | Afirmativa para PCD's", "alta", "estrategia_dados"),
    ("Analista de Cobrança Pleno", "alta", "operacao_interna"),
    ("Assistente de Contas a Receber", "alta", "operacao_interna"),
    # falsos positivos reais do filtro da v0.3
    ("Grupo QuintoAndar | Banco de Talentos | Analista de Crédito Imobiliário", "descartar", None),
    ("CREDIT ANALYST I | CORPORATE CREDIT ANALYSIS", "descartar", None),
    ("Gerente de Relacionamento | C6 Empresas - Pessoa Jurídica | Curitiba - Paraná", "descartar", None),
    ("Site Reliability Engineer - Disaster Recovery", "descartar", None),
    ("Data Collection Analyst", "descartar", None),
])
def test_classify_by_title(title, expected, role):
    r = classify_job(title, description="menciona cobrança e collections na descrição", location="São Paulo, SP")
    assert r["relevance"] == expected
    if role:
        assert r["role_type"] == role


def test_foreign_location_goes_to_review():
    assert classify_job("Collections Analyst", location="Mexico City, Mexico")["relevance"] == "revisar"


def test_strip_html_handles_escaped_greenhouse_content():
    raw = "&lt;div class=&quot;x&quot;&gt;&lt;p&gt;Sobre a &lt;strong&gt;Stone&lt;/strong&gt;&lt;/p&gt;&lt;/div&gt;"
    assert strip_html(raw) == "Sobre a Stone"


def test_competitor_scores_zero():
    assert score_job({"competitor": True, "relevance": "alta"})[0] == 0


def test_config_merges_file_and_env(tmp_path):
    f = tmp_path / "b.json"
    f.write_text(json.dumps({"boards": [{"provider": "greenhouse", "token": "a", "company_name": "A"}]}))
    boards = jobboards.configured_boards('[{"provider":"lever","token":"b","company_name":"B"},{"provider":"greenhouse","token":"a","company_name":"A"}]', path=f)
    assert [(b["provider"], b["token"]) for b in boards] == [("greenhouse", "a"), ("lever", "b")]
    with pytest.raises(ValueError):
        jobboards.configured_boards('[{"provider":"gupy","token":"x","company_name":"X"}]', path=f)


def test_fetch_paginates_lever_and_cleans_greenhouse(monkeypatch):
    monkeypatch.setattr(jobboards, "LEVER_PAGE", 2)
    def handler(req):
        if req.url.host == "boards-api.greenhouse.io":
            return httpx.Response(200, json={"jobs": [
                {"id": 1, "title": "Analista de Cobrança", "absolute_url": "https://x/1", "location": {"name": "Manaus, AM"},
                 "content": "&lt;p&gt;Rotina de cobrança&lt;/p&gt;"},
                {"id": 2, "title": "Gerente de Relacionamento", "absolute_url": "https://x/2", "content": "cobrança"}]})
        skip = int(req.url.params["skip"])
        pages = {0: [{"id": "a", "text": "Dev", "hostedUrl": "https://l/a"}, {"id": "b", "text": "Dev 2", "hostedUrl": "https://l/b"}],
                 2: [{"id": "c", "text": "Collections Specialist", "hostedUrl": "https://l/c", "categories": {"location": "Remoto"}}]}
        return httpx.Response(200, json=pages.get(skip, []))
    real = httpx.Client
    monkeypatch.setattr(jobboards.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler)))
    out = jobboards.fetch_job_opportunities([{"provider": "greenhouse", "token": "g", "company_name": "G"},
                                             {"provider": "lever", "token": "l", "company_name": "L"}])
    keys = {r["source_key"] for r in out["records"]}
    assert keys == {"job:greenhouse:g:1", "job:lever:l:c"}  # 3ª vaga do Lever veio da 2ª página
    assert out["jobs_read"] == 5 and "&lt;" not in out["records"][0]["description"]
    assert out["discarded_samples"][0]["motivo"] == "termo só na descrição da vaga"
