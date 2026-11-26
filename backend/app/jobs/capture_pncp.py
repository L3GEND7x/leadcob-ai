"""Run the official PNCP publication capture from a scheduled worker."""
import argparse
import json

from app.api.routes import capture_pncp
from app.db.database import SessionLocal, check_schema_revision


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days', type=int, default=2)
    parser.add_argument('--max-pages', type=int, default=5)
    parser.add_argument('--probe', action='store_true', help='Read PNCP only; no database access or writes')
    args = parser.parse_args(argv)
    if not 1 <= args.days <= 30 or not 1 <= args.max_pages <= 5:
        parser.error('days must be 1..30 and max-pages must be 1..5')
    if args.probe:
        from app.collectors.pncp import scan_publications
        result = scan_publications(days=args.days, max_pages=args.max_pages)
        print(json.dumps({key: result[key] for key in (
            'pages_read', 'records_read', 'total_available', 'coverage_complete', 'date_from', 'date_to'
        )} | {'database_written': False, 'errors_count': len(result['errors'])}), flush=True)
        if not result['coverage_complete']:
            raise SystemExit(2 if result['pages_read'] else 1)
        return
    check_schema_revision()
    with SessionLocal() as db:
        result = capture_pncp(
            mode="varredura", only_open=True, include_review=True,
            max_pages=args.max_pages, days=args.days, db=db,
        )
    print(json.dumps({key: result[key] for key in (
        "run_id", "status", "pages_read", "created", "updated", "proven",
    )}), flush=True)
    # A scheduler must observe partial coverage as a non-successful run.
    if result['status'] != 'completed':
        raise SystemExit(2 if result['status'] == 'partial' else 1)


if __name__ == "__main__":
    main()
