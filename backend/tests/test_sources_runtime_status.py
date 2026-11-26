from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes import sources
from app.db.database import Base
from app.db.models import CaptureRun


@pytest.mark.parametrize("status,label", [
    ("running", "Coleta em andamento"),
    ("partial", "Coleta parcial"),
    ("failed", "Com erro de coleta"),
    ("completed", "Coleta concluída"),
])
def test_source_catalog_distinguishes_runtime_collection(status, label):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        historical = sources(category=None, db=db)["sources"]
        pncp = [s for s in historical if s["category"] == "integrada" and s["name"].startswith("PNCP")]
        assert pncp
        assert all(s["display_status"] == "Integrada — validação histórica" and "last_run" not in s for s in pncp)
        db.add_all([
            CaptureRun(source_name="PNCP — busca", status="completed",
                       started_at=now - timedelta(days=1), records_seen=10),
            CaptureRun(source_name="PNCP — busca", status=status,
                       started_at=now, records_seen=4, records_created=1,
                       message="Registro de teste"),
        ])
        db.commit()
        items = sources(category="integrada", db=db)["sources"]
        pncp = [s for s in items if s["name"].startswith("PNCP")]
        assert all(s["display_status"] == label for s in pncp)
        assert all(s["last_run"]["scope"] == "family" for s in pncp)
        assert all(s["last_run"]["records_seen"] == 4 for s in pncp)
        assert all(s["last_run"]["records_created"] == 1 for s in pncp)
        assert all(("last_error" in s) == (status in ("failed", "partial")) for s in pncp)
        jobs = [s for s in items if s["name"].startswith(("Greenhouse", "Lever"))]
        assert jobs and all(s["display_status"] == "Integrada — validação histórica" for s in jobs)
    engine.dispose()
