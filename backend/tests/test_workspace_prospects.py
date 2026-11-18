from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from app.services import workspace_prospects as p


def test_lookup_scope_and_privacy(monkeypatch):
    auth=Mock(return_value=SimpleNamespace(organization_id=7))
    monkeypatch.setattr(p,"authorize",auth)
    monkeypatch.setattr(p,"check_subscription",Mock())
    provider=Mock(return_value={"cnpj":"11222333000181","razao_social":"Fixture Ltda",
        "natureza_juridica":"Sociedade Empresária Limitada","situacao_cadastral":"ATIVA",
        "source":"Fixture","email":"private@example.test","qsa":[{"name":"Private"}]})
    monkeypatch.setattr(p.cnpj_api,"lookup",provider)
    db=Mock()
    db.get.return_value=None
    result=p.lookup(db,"token",7,"11.222.333/0001-81")
    assert result["cnpj"]=="11222333000181"
    assert "email" not in result and "qsa" not in result
    assert auth.call_count==2
    assert db.get.call_args.args[1]==(7,"11222333000181")
    db.get.return_value=object()
    with pytest.raises(HTTPException) as e:
        p.lookup(db,"token",7,"11222333000181")
    assert e.value.status_code==409
    assert provider.call_count==1
    db.get.return_value=None
    provider.return_value["natureza_juridica"]="Empresário (Individual)"
    with pytest.raises(HTTPException) as e:
        p.lookup(db,"token",7,"11222333000181")
    assert e.value.status_code==422
