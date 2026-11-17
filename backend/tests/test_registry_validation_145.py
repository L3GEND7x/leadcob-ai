from datetime import datetime, timedelta, timezone
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import Company
from app.collectors import cnpj_api
from app.services.registry_coverage import registry_coverage


def test_wrong_cnpj_cannot_be_returned(monkeypatch):
    key="11222333000181"
    monkeypatch.setattr(cnpj_api,"PROVIDERS",[("A","https://a.test/{cnpj}"),("B","https://b.test/{cnpj}")])
    def respond(request):
        return httpx.Response(200,json={"cnpj":"00000000000000" if request.url.host=="a.test" else key,
                                       "razao_social":"Fixture"})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert cnpj_api.lookup(key,http=client,attempts=1,pause=0)["source"]=="B"
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={"cnpj":"00000000000000","razao_social":"Wrong"}))) as client:
        with pytest.raises(cnpj_api.CNPJUnavailable):
            cnpj_api.lookup(key,http=client,attempts=1,pause=0)


def test_registry_age_latest_local_update():
    engine=create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        now=datetime.now(timezone.utc)
        for age in (180,10):
            db.add(Company(name="Fixture",cnpj="11222333000181",city="Manaus",state="AM",
                           registry_source="Fixture",registry_updated_at=now-timedelta(days=age)))
        db.commit()
        r=registry_coverage(db)
        assert r["registry_update_age"]=={"missing":0,"future_date":0,"within_90_days":1,"older_than_90_days":0}
    engine.dispose()
