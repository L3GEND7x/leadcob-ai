from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_assistant_is_not_exposed_in_primary_navigation():
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    assert "Assistente LeadCob" not in index
    assert '#/assistente' not in index
    assert 'src="/static/assistant.js"' not in index
    assert "assistente: viewAssistente" not in app

    # The commercial flow remains visible and ordered around action.
    assert index.index("Central de comando") < index.index("Inteligência do dia")
    assert index.index("Sinais e oportunidades") < index.index("Encontrar empresas")
    assert index.index("Contatos empresariais") < index.index("CRM comercial")
    assert index.index("CRM comercial") < index.index("Relatórios")
