"""Run the official PNCP publication capture from a scheduled worker."""
import json

from app.api.routes import capture_pncp
from app.db.database import SessionLocal, check_schema_revision


def main():
    check_schema_revision()
    with SessionLocal() as db:
        result = capture_pncp(
            mode="varredura", only_open=True, include_review=True,
            max_pages=5, days=2, db=db,
        )
    print(json.dumps({key: result[key] for key in (
        "run_id", "status", "pages_read", "created", "updated", "proven",
    )}), flush=True)


if __name__ == "__main__":
    main()
