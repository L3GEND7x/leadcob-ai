from app.jobs import national_registry_preflight as job
from app.services.cnpj import _dv, WEIGHTS_1, WEIGHTS_2
import pytest


def row(i,uf="AM",municipality="0255",status="02",cnae="4631100",branch="1"):
    base=f"{i:08d}"+"0001"
    dv=_dv(base,WEIGHTS_1)
    r=[""]*30
    r[0],r[1],r[2]=base[:8],base[8:],dv+_dv(base+dv,WEIGHTS_2)
    r[3],r[4],r[5]=branch,"Fixture sensitive name",status
    r[11],r[19],r[20]=cnae,uf,municipality
    r[27]="private@example.test"
    return r


def test_one_pass_sizing_counts_all_ufs_and_branches():
    rows=[row(1),row(2,branch="2"),row(3,municipality="0256"),
          row(4,uf="SP"),row(5,status="08"),row(6,cnae="9700500"),
          row(7,uf="EX"),["bad"]]
    report=job.assess(iter(rows),max_records=1)
    assert report["records_read"]==8
    assert len(report["by_uf"])==27
    assert report["candidate_rows"]==4
    assert report["by_uf"]["AM"]["candidates_before_company_join"]==3
    assert report["by_uf"]["AM"]["exceeds_limit"] is True
    assert report["by_uf"]["AM"]["municipalities_exceeding_limit"]==["0255"]
    assert report["by_uf"]["SP"]["candidates_before_company_join"]==1
    assert report["unrecognized_uf_candidates"]==1
    assert report["bad_layout"]==1
    assert report["coverage_complete"] is False
    assert "Fixture sensitive name" not in str(report)
    assert "private@example.test" not in str(report)


def test_invalid_dv_and_unknown_municipality():
    invalid=row(1)
    invalid[2]="AA"
    report=job.assess([invalid,row(2,municipality="secret text")])
    assert report["invalid_cnpjs"]==1
    assert report["by_uf"]["AM"]["municipality_candidates"]=={"unknown":1}
    assert "secret text" not in str(report)


def test_cli_reads_one_partition(monkeypatch,tmp_path):
    calls=[]
    class FakeSource:
        def __init__(self, release,http,local_dir):
            assert release=="2026-10"
            assert http is None
        def rows(self,name):
            calls.append(name)
            return iter([row(1),row(2,uf="SP")])
    monkeypatch.setattr(job,"Source",FakeSource)
    result=job.main(["--release","2026-10","--part","4","--local-dir",str(tmp_path)])
    assert calls==["Estabelecimentos4.zip"]
    assert result["candidate_rows"]==2
    with pytest.raises(SystemExit):
        job.main(["--release","2026-10","--part","4","--max-records","0"])
