from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
import pytest

from app.db.database import Base
from app.db.models import Company, Suppression
from app.jobs import import_national_registry as job
from app.services.cnpj import _dv, WEIGHTS_1, WEIGHTS_2


def record(i, uf="AM", **changes):
    base = f"{i:012d}"
    dv = _dv(base, WEIGHTS_1)
    return dict(cnpj=base+dv+_dv(base+dv, WEIGHTS_2), razao_social="Fixture LTDA",
                uf=uf, situacao_cadastral="ATIVA", natureza_codigo="2062",
                natureza_juridica="Sociedade Empresária Limitada",
                cnae_principal="4631100", municipio="Manaus", **changes)


def test_all_states_and_preview_without_writing(monkeypatch):
    assert len(job.UFS) == 27
    calls = []
    def collect(opts):
        calls.extend(opts)
        return [record(1, "SP")]
    monkeypatch.setattr(job.import_cnpj, "main", collect)
    report = job.main(["--uf", "SP", "--part", "0", "--release", "2026-10"])
    assert report["mode"] == "preview"
    assert report["eligible"] == 1
    assert report["coverage_complete"] is False
    assert report["profiles"] == {"atacado": 1}
    assert "--include-branches" in calls and "--min-size" not in calls
    assert "--strict-layout" in calls and "--dry-run" in calls


def test_bad_or_duplicate_records_fail_before_writes():
    for changes in ({"natureza_codigo":"2135"}, {"situacao_cadastral":"BAIXADA"},
                    {"cnpj":"00000000000000"}, {"razao_social":"Fixture 12345678901"},
                    {"cnae_principal":"9700500"}, {"uf":"SP"}):
        row = record(1)
        row.update(changes)
        with pytest.raises(ValueError):
            job.prepare([row], "AM")
    with pytest.raises(ValueError):
        job.prepare([record(1), record(1)], "AM")


def test_insert_only_preserves_crm_and_suppression_on_rerun():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    rows = job.prepare([record(1), record(2), record(3)], "AM")
    with Session(engine) as db:
        db.add(Company(cnpj=rows[0]["cnpj"], name="Existing", notes="Preserve",
                       pipeline_stage="proposta"))
        db.add(Suppression(cnpj=rows[1]["cnpj"], reason="Opt-out"))
        db.commit()
        assert job.insert_missing(db, rows, "2026-10", batch_size=1) == {
            "created": 1, "existing": 1, "suppressed": 1}
        assert job.insert_missing(db, rows, "2026-10", batch_size=2) == {
            "created": 0, "existing": 2, "suppressed": 1}
        companies = {c.cnpj:c for c in db.scalars(select(Company))}
        assert len(companies) == 2
        assert companies[rows[0]["cnpj"]].notes == "Preserve"
        assert companies[rows[0]["cnpj"]].pipeline_stage == "proposta"
        assert companies[rows[2]["cnpj"]].institutional_email is None
        assert companies[rows[2]["cnpj"]].registry_source.endswith("2026-10")
    engine.dispose()
