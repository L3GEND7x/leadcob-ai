import pytest

from app.collectors import jobboards


@pytest.mark.parametrize("provider,payload", [
    ("greenhouse", {}),
    ("greenhouse", {"jobs": None}),
    ("greenhouse", {"jobs": ["invalid"]}),
    ("lever", {"error": "invalid"}),
    ("lever", [None]),
])
def test_invalid_board_response_is_not_successful_empty_board(monkeypatch,provider,payload):
    monkeypatch.setattr(jobboards,"_get",lambda *a,**kw:payload)
    board={"provider":provider,"token":"fixture","company_name":"Empresa teste"}
    result=jobboards.fetch_job_opportunities([board])
    assert result["boards_fetched"] == []
    assert result["jobs_read"] == 0
    assert len(result["errors"]) == 1


@pytest.mark.parametrize("provider,payload", [
    ("greenhouse", {"jobs": []}), ("lever", []),
])
def test_valid_empty_board_is_successful(monkeypatch,provider,payload):
    monkeypatch.setattr(jobboards,"_get",lambda *a,**kw:payload)
    result=jobboards.fetch_job_opportunities([
        {"provider":provider,"token":"fixture","company_name":"Empresa teste"}
    ])
    assert result["boards_fetched"] == [f"job:{provider}:fixture:"]
    assert result["errors"] == []


def test_lever_pagination_never_marks_truncated_board_fetched(monkeypatch):
    monkeypatch.setattr(jobboards,"LEVER_MAX_PAGES",2)
    monkeypatch.setattr(jobboards,"LEVER_PAGE",1)
    calls=[]
    def full_page(client,url,params):
        calls.append(params["skip"])
        return [{"id":str(params["skip"]),"text":"Vaga teste"}]
    monkeypatch.setattr(jobboards,"_get",full_page)
    result=jobboards.fetch_job_opportunities([
        {"provider":"lever","token":"fixture","company_name":"Empresa teste"}
    ])
    assert calls == [0,1]
    assert result["boards_fetched"] == []
    assert len(result["errors"]) == 1
