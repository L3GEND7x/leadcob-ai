from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import Company, BusinessContact
from app.services.contact_targets import targets


def test_missing_channel_targets_and_duplicates():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        a = Company(name="Fixture A",cnpj="11222333000181",city="Manaus",state="AM",
                    registration_status="ATIVA",website="https://example.com",legal_nature="Sociedade Empresária Limitada")
        b = Company(name="Fixture duplicate",cnpj=a.cnpj,city="Manaus",state="AM",
                    registration_status="ATIVA",website=a.website,legal_nature="Sociedade Empresária Limitada")
        db.add_all([a,b]);db.commit()
        r=targets(db,"AM","Manaus","email")
        assert r["active_unique_cnpjs"]==1
        assert r["active_corporate_cnpjs"]==1
        assert r["missing_channel"]==1
        assert r["ready_for_site_discovery"]==1
        assert r["items"][0]["company_id"]==a.id
        db.add(BusinessContact(company_id=b.id,kind="email",value="contato@example.com",
                               source_name="Fixture",status="a_verificar",department="geral"))
        db.commit()
        r=targets(db,"AM","Manaus","email")
        assert r["with_channel"]==1
        assert r["with_verified_channel"]==0
        assert r["missing_channel"]==0
        assert targets(db,"AM","Manaus","phone")["missing_channel"]==1
    engine.dispose()



def test_targets_exclude_individual_unknown_and_conflicted_cnpj_status():
    from app.services.cnpj import _dv, WEIGHTS_1, WEIGHTS_2
    from app.db.models import Suppression
    from app.services.contact_readiness import contactability
    from app.services.contact_targets import targets

    def cnpj(seed):
        base = f"{seed:012d}"
        first = _dv(base, WEIGHTS_1)
        return base + first + _dv(base + first, WEIGHTS_2)

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    corp = "Sociedade Empresária Limitada"
    with Session(engine) as db:
        # Invalid role mailbox is a missing institutional channel, not a lead ready to message.
        companies = [
            (11, 11, "ATIVA", corp, "https://firm.example"),
            (12, 12, "ATIVA", corp, "http://localhost:80"),  # not safe for discovery
            (13, 13, "ATIVA", "Empresário Individual", "https://individual.example"),
            (14, 14, "ATIVA", corp, "https://conflict.example"),
            (15, 14, "BAIXADA", corp, "https://conflict.example"),
            (16, 16, "ATIVA", corp, "https://blocked.example"),
            (17, 16, "ATIVA", corp, "https://blocked.example"),
        ]
        for id_, num, status, nature, website in companies:
            db.add(Company(
                id=id_, name=f"Empresa {id_}", cnpj=cnpj(num),
                state="AM", city="Manaus", registration_status=status,
                legal_nature=nature, website=website))
        db.flush()
        db.add(Suppression(company_id=16, reason="opt-out teste"))
        for cid, kind, value, status, url in [
            (11, "email", "joao.silva@firm.example", "verificado", "https://firm.example"),
            (12, "email", "financeiro@firm.example", "a_verificar", "https://firm.example"),
            (13, "email", "contato@individual.example", "verificado", "https://individual.example"),
            (14, "email", "contato@conflict.example", "verificado", "https://conflict.example"),
            (17, "email", "financeiro@blocked.example", "verificado", "https://blocked.example"),
        ]:
            db.add(BusinessContact(company_id=cid, kind=kind, value=value,
                                   status=status, source_name="Fixture institucional",
                                   source_url=url))
        db.commit()

        report = contactability(db)
        candidates = targets(db, "AM", "Manaus", "email", limit=20)
        assert report["active_unique_cnpjs"] == 3
        assert report["active_corporate_cnpjs"] == 2
        assert candidates["active_unique_cnpjs"] == report["active_unique_cnpjs"]
        assert candidates["active_corporate_cnpjs"] == report["active_corporate_cnpjs"]
        assert candidates["with_channel"] == 1
        assert candidates["with_verified_channel"] == 0
        assert candidates["missing_channel"] == 1
        assert {row["company_id"] for row in candidates["items"]} == {11}
        assert candidates["items"][0]["reason"] == "registered_site"
        # Website candidate from localhost is never marked ready.
        website_candidates = targets(db, "AM", "Manaus", "website")
        second = next(row for row in website_candidates["items"]
                      if row["company_id"] == 12)
        assert second["reason"] == "invalid_site"
        assert second["discovery_ready"] is False
        assert all(row["company_id"] not in (13, 14, 15, 16, 17)
                   for row in website_candidates["items"])
    engine.dispose()
