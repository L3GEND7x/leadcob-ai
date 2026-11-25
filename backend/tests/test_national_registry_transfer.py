import sqlite3

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import Company, Suppression
from app.jobs import national_registry_stage as stage, national_registry_transfer as job
from app.services.cnpj import _dv, WEIGHTS_1, WEIGHTS_2


def key(root, order="0001"):
    base=root+order
    dv=_dv(base,WEIGHTS_1)
    return base+dv+_dv(base+dv,WEIGHTS_2)


@pytest.fixture
def prepared(tmp_path):
    path=tmp_path/"stage.sqlite"
    db=stage.connect(path)
    stage.init(db,"2026-10",None)
    with db:
        db.executemany("INSERT INTO entities VALUES(?,?,?,?,?,?)",[
            ("11111111",1,"Fixture A LTDA","2062","DEMAIS",100.0),
            ("22222222",1,"Fixture B LTDA","2062","DEMAIS",200.0),
            ("33333333",0,None,None,None,None)])
        rows=[(key("11111111"),"11111111","AM","0255","4631100","","2020-01-01","atacado",0),
              (key("11111111","0002"),"11111111","AM","0255","4631100","","2020-01-01","atacado",0),
              (key("22222222"),"22222222","AM","0255","4631100","4711300",None,"atacado",0),
              (key("33333333"),"33333333","AM","0255","4631100","",None,"atacado",0),
              (key("22222222","0002"),"22222222","SP","7107","4631100","",None,"atacado",0)]
        db.executemany("INSERT INTO establishments VALUES(?,?,?,?,?,?,?,?,?)",rows)
        db.executemany("INSERT INTO files VALUES(?,?)",[(f,"{}") for f in stage.FILES])
    yield db,path
    db.close()


LOOKUPS=({"0255":"Manaus","7107":"São Paulo"},{"4631100":"Atacado"},{"2062":"Sociedade Empresária Limitada"})


def test_preview_paginates_and_reconciles_without_target(prepared):
    db,path=prepared
    report=job.transfer(db,"AM",0,LOOKUPS,"2026-10",batch_size=1)
    assert report["candidates"]==4
    assert report["eligible"]==report["validated"]==3
    assert report["excluded_identity"]==1
    assert report["mode"]=="preview"
    assert report["coverage_complete"] is False
    assert "created" not in report
    pages=list(job.batches(db,"AM",0,LOOKUPS,2))
    assert [len(page) for page in pages]==[2,1]
    assert all(r["municipio"]=="Manaus" for page in pages for r in page)
    assert len({r["cnpj"] for page in pages for r in page})==3
    assert job.transfer(db,"SP",0,LOOKUPS,"2026-10")["validated"]==1


def test_transfer_preserves_existing_and_suppression_on_retry(prepared):
    db,path=prepared
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as target:
        target.add(Company(cnpj=key("11111111"),name="Existing",notes="Preserve",pipeline_stage="proposta"))
        target.add(Suppression(cnpj=key("11111111","0002"),reason="opt-out"))
        target.commit()
        first=job.transfer(db,"AM",0,LOOKUPS,"2026-10",target,batch_size=1)
        assert (first["created"],first["existing"],first["suppressed"])==(1,1,1)
        second=job.transfer(db,"AM",0,LOOKUPS,"2026-10",target,batch_size=2)
        assert (second["created"],second["existing"],second["suppressed"])==(0,2,1)
        records={r.cnpj:r for r in target.scalars(select(Company))}
        assert len(records)==2
        assert records[key("11111111")].notes=="Preserve"
        assert records[key("11111111")].pipeline_stage=="proposta"
        new=records[key("22222222")]
        assert new.city=="Manaus" and new.cnae_secondary=="4711300"
        assert new.institutional_email is None
    engine.dispose()


def test_missing_lookup_or_identity_blocks_transfer(prepared):
    db,path=prepared
    with pytest.raises(ValueError,match="referência"):
        job.transfer(db,"AM",0,({},LOOKUPS[1],LOOKUPS[2]),"2026-10")
    with db:
        db.execute("DELETE FROM entities WHERE root='22222222'")
    with pytest.raises(ValueError,match="conciliação"):
        job.transfer(db,"AM",0,LOOKUPS,"2026-10")


def test_readonly_release_and_incomplete_stage(prepared):
    db,path=prepared
    reader=job.open_readonly(path)
    try:
        assert job.config_for(reader,"2026-10")["version"]==1
        with pytest.raises(sqlite3.OperationalError):
            reader.execute("DELETE FROM entities")
        with pytest.raises(ValueError,match="Competência"):
            job.config_for(reader,"2026-09")
    finally:
        reader.close()
    with db:
        db.execute("DELETE FROM files WHERE name='Empresas0.zip'")
    with pytest.raises(ValueError,match="incompleto"):
        job.config_for(db,"2026-10")


def test_cli_preview_and_explicit_apply_gate(prepared,monkeypatch):
    db,path=prepared
    monkeypatch.setattr(job,"load_lookups",lambda config:LOOKUPS)
    args=["--stage",str(path),"--release","2026-10","--uf","AM","--part","0"]
    assert job.main(args)["validated"]==3
    with pytest.raises(SystemExit):
        job.main(args+["--apply"])
