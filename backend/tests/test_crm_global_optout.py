"""Global opt-out must also protect legacy CRM search, export and interactions."""
from fastapi.testclient import TestClient
from app.db.database import SessionLocal, ensure_schema
from app.db.models import Company, Suppression
from app.main import app
from app.services.cnpj import _dv, WEIGHTS_1, WEIGHTS_2
from app.services.crm import suppression_for


def test_crm_excludes_duplicate_cnpj_with_id_only_optout():
    ensure_schema()
    base = "ZZ9900000001"
    first_dv = _dv(base, WEIGHTS_1)
    cnpj = base + first_dv + _dv(base + first_dv, WEIGHTS_2)
    marker = "GLOBAL OPT OUT REGRESSION"
    with SessionLocal() as db:
        first = Company(name=marker+" A", cnpj=cnpj, state="AP", city="MACAPA")
        duplicate = Company(name=marker+" B", cnpj=cnpj.lower(), state="AP", city="MACAPA")
        db.add_all([first, duplicate])
        db.flush()
        ids = [first.id, duplicate.id]
        suppression = Suppression(company_id=first.id, reason="opt-out")
        db.add(suppression)
        db.commit()
        sid = suppression.id
    try:
        with SessionLocal() as db:
            assert suppression_for(db, db.get(Company, ids[1])).id == sid
        with TestClient(app) as client:
            for sort in ("name", "score", "capital", "recent"):
                res = client.get("/api/companies/search", params={"q":marker,"sort":sort})
                assert res.status_code == 200
                assert res.json()["total"] == 0
                assert res.json()["items"] == []
            res = client.get("/api/companies/search",params={"q":cnpj,"sort":"name","include_suppressed":True})
            assert res.status_code == 200
            assert {row["id"] for row in res.json()["items"]} == set(ids)
            assert all(row["suppressed"] for row in res.json()["items"])
            assert client.post(f"/api/companies/{ids[1]}/interactions",
                               json={"kind":"contato","summary":"Não enviar"}).status_code == 409
            exported = client.get("/api/export/companies.csv",params={"uf":"AP"})
            assert exported.status_code == 200 and marker not in exported.text
    finally:
        with SessionLocal() as db:
            db.query(Suppression).filter(Suppression.id == sid).delete(synchronize_session=False)
            db.query(Company).filter(Company.id.in_(ids)).delete(synchronize_session=False)
            db.commit()
