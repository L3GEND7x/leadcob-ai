from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]/'frontend'


def test_subscription_ui_assets():
    owner=(ROOT/'commercial-admin.html').read_text(encoding='utf-8')
    client=(ROOT/'commercial.html').read_text(encoding='utf-8')
    assert 'id="create-plan"' in owner
    assert 'id="plan-rows"' in owner
    assert 'data-module="subscription"' in client
    assert '/static/commercial-admin.js' in owner
    assert '/static/commercial.js' in client
    assert '/subscription' in (ROOT/'commercial-admin.js').read_text(encoding='utf-8')
    assert "workspace('subscription')" in (ROOT/'commercial.js').read_text(encoding='utf-8')
