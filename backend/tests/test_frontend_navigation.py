from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_assistant_is_wired_in_owner_navigation():
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    assert '#/assistente' in index
    assert 'src="/static/assistant.js"' in index
    assert index.index('src="/static/assistant.js"') < index.index('src="/static/app.js"')
    assert "assistente: viewAssistente" in app
    commercial = (ROOT / "frontend" / "commercial.html").read_text(encoding="utf-8")
    assert '#/assistente' not in commercial
    assert 'src="/static/assistant.js"' not in commercial

    # The commercial flow remains visible and ordered around action.
    assert index.index("Central de comando") < index.index("Inteligência do dia")
    assert index.index("Sinais e oportunidades") < index.index("Encontrar empresas")
    assert index.index("Contatos empresariais") < index.index("CRM comercial")
    assert index.index("CRM comercial") < index.index("Relatórios")
