from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_assistant_is_removed_from_owner_navigation():
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    assert '#/assistente' not in index
    assert 'src="/static/assistant.js"' not in index
    assert "assistente: viewAssistente" not in app
    assert "history.replaceState(null, '', '#/inicio')" in app
    commercial = (ROOT / "frontend" / "commercial.html").read_text(encoding="utf-8")
    commercial_js = (ROOT / "frontend" / "commercial.js").read_text(encoding="utf-8")
    assert '#/assistente' not in commercial
    assert 'src="/static/assistant.js"' not in commercial
    assert 'data-module="assistant"' not in commercial
    assert "Inteligência da organização" not in commercial
    assert "current==='assistant'" not in commercial_js
    assert "assistant/generate" not in commercial_js

    # The commercial flow remains visible and ordered around action.
    assert index.index("Central de comando") < index.index("Inteligência do dia")
    assert index.index("Sinais e oportunidades") < index.index("Encontrar empresas")
    assert index.index("Contatos empresariais") < index.index("CRM comercial")
    assert index.index("CRM comercial") < index.index("Relatórios")


def test_owner_dashboard_explains_crm_and_loads_municipality():
    app = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert "Empresas cadastradas não são leads qualificados" in app
    assert 'href="/owner/discovery">Localizar canais institucionais' in app
    assert "if (!PUBLISHED) await loadMunicipalCommand(municipalForm);" in app
