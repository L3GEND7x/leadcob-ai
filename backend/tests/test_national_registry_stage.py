import sqlite3
import pytest

from app.jobs import national_registry_stage as stage
from app.services.cnpj import _dv, WEIGHTS_1, WEIGHTS_2


def est(root, uf="AM", order="0001", status="02"):
    base=root+order
    dv=_dv(base,WEIGHTS_1)
    row=[""]*30
    row[0],row[1],row[2]=root,order,dv+_dv(base+dv,WEIGHTS_2)
    row[3],row[4],row[5]="1","Private trade name",status
    row[10],row[11],row[19],row[20]="20200101","4631100",uf,"0255"
    row[27]="private@example.test"
    return row


def emp(root,name,nature="2062"):
    return [root,name,nature,"49","1000,00","03",""]


class Source:
    def __init__(self, files):
        self.files=files
        self.calls=[]
    def rows(self,name):
        self.calls.append(name)
        return iter(self.files.get(name,[]))


def test_stage_resume_privacy_and_reconciliation(tmp_path):
    path=tmp_path/"stage.sqlite"
    src=Source({"Empresas0.zip":[emp("11111111","Fixture LTDA"),
                                emp("22222222","Private Person 12345678901","2135")],
                "Estabelecimentos0.zip":[est("11111111"),est("11111111",order="0002"),
                                          est("22222222"),est("33333333"),est("44444444",status="08")]})
    db=stage.connect(path)
    stage.init(db,"2026-10",None)
    stage.stage_file(db,src,"Empresas0.zip")
    db.close()
    db=stage.connect(path)
    stage.init(db,"2026-10",None)
    assert stage.stage_file(db,src,"Empresas0.zip")["already_staged"]
    assert src.calls==["Empresas0.zip"]
    with pytest.raises(ValueError):
        stage.reconciliation(db,"AM",0)
    for name in stage.FILES:
        stage.stage_file(db,src,name)
    assert len(src.calls)==20
    assert stage.status(db)["staging_complete"]
    assert stage.reconciliation(db,"AM",0)==dict(uf="AM",part=0,candidates=4,
        unresolved=1,excluded_identity=1,eligible=2,coverage_complete=False)
    assert db.execute("SELECT name,nature,size,capital FROM entities WHERE root='22222222'").fetchone()==(None,None,None,None)
    dump="\n".join(db.iterdump())
    assert "Private Person" not in dump and "private@example.test" not in dump
    assert "Private trade name" not in dump
    db.close()


def test_file_atomic_rollback_and_retry(tmp_path):
    db=stage.connect(tmp_path/"stage.sqlite")
    stage.init(db,"2026-10",None)
    src=Source({"Empresas0.zip":[emp("11111111","Fixture LTDA"),["invalid"]]})
    with pytest.raises(ValueError):
        stage.stage_file(db,src,"Empresas0.zip")
    assert db.execute("SELECT count(*) FROM entities").fetchone()[0]==0
    assert not stage.status(db)["completed_files"]
    src.files["Empresas0.zip"]=[emp("11111111","Fixture LTDA")]
    stage.stage_file(db,src,"Empresas0.zip")
    src.files["Empresas1.zip"]=[emp("11111111","Duplicate")]
    with pytest.raises(sqlite3.IntegrityError):
        stage.stage_file(db,src,"Empresas1.zip")
    assert stage.status(db)["completed_files"]==["Empresas0.zip"]
    assert db.execute("SELECT name FROM entities").fetchone()[0]=="Fixture LTDA"
    with pytest.raises(ValueError):
        stage.init(db,"2026-11",None)
    db.close()


def test_bad_establishment_rolls_back_partition(tmp_path):
    db=stage.connect(tmp_path/"stage.sqlite")
    stage.init(db,"2026-10",None)
    bad=est("22222222")
    bad[2]="AA"
    src=Source({"Estabelecimentos0.zip":[est("11111111"),bad]})
    with pytest.raises(ValueError):
        stage.stage_file(db,src,"Estabelecimentos0.zip")
    assert db.execute("SELECT count(*) FROM establishments").fetchone()[0]==0
    assert not stage.status(db)["completed_files"]
    db.close()
