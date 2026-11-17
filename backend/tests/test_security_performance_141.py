import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core import security
from app.core.config import settings
from app.db.database import Base
from app.db.models import Company
from app.services.lead_qualification import qualification
from app.services.cnpj import _dv, WEIGHTS_1, WEIGHTS_2


def test_production_case_cannot_bypass_auth(monkeypatch):
    monkeypatch.setattr(settings,"app_env"," Production ")
    monkeypatch.setattr(settings,"admin_password_hash","")
    assert security.auth_enabled()
    with pytest.raises(RuntimeError):
        security.validate_configuration()


def test_ranking_pagination_preserves_population():
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for i in range(1,121):
            base=f"{i:012d}"
            first=_dv(base,WEIGHTS_1)
            cnpj=base+first+_dv(base+first,WEIGHTS_2)
            db.add(Company(name=f"Fixture {i}",cnpj=cnpj,city="Manaus",state="AM"))
        db.commit()
        all_rows=qualification(db,"AM","Manaus",limit=120)
        page=qualification(db,"AM","Manaus",limit=10,offset=25)
        assert page["items"]==all_rows["items"][25:35]
        assert page["total"]==all_rows["total"]==120
        assert page["counts"]==all_rows["counts"]
        assert page["contact_coverage"]==all_rows["contact_coverage"]
    engine.dispose()
