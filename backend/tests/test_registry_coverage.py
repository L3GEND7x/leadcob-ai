from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import Company
from app.services.registry_coverage import registry_coverage


def test_registry_coverage_counts_records_and_unique_cnpjs():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            Company(name="A", city="Manaus", state="AM", cnpj="11222333000181",
                    registration_status="ATIVA", registry_source="test",
                    registry_updated_at=datetime.now(timezone.utc)),
            Company(name="A duplicate", city=" MANAUS ", state="am", cnpj="11222333000181",
                    registration_status="BAIXADA"),
            Company(name="Missing", city="Manaus", state="AM"),
            Company(name="Invalid", city="Manaus", state="AM", cnpj="00000000000000"),
            Company(name="Outside", city="Manacapuru", state="AM", cnpj="11222333000181"),
        ])
        db.commit()
        result = registry_coverage(db)
        assert result["company_records"] == 4
        assert result["unique_valid_cnpjs"] == 1
        assert result["duplicate_valid_records"] == 1
        assert result["missing_cnpj_records"] == 1
        assert result["invalid_cnpj_records"] == 1
        assert result["conflicting_status_cnpjs"] == 1
        assert result["active_cnpjs"] == 0
        assert result["with_registry_source_and_date"] == 1
        assert result["market_coverage_pct"] is None
    engine.dispose()
