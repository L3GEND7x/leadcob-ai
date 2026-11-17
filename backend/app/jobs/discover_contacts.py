"""Run explicitly with python -m app.jobs.discover_contacts --max-items 20."""
import argparse
import time
from app.db.database import SessionLocal, check_schema_revision
from app.services.contact_discovery_queue import run_one
from app.core.config import settings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-items',type=int,default=20)
    args=parser.parse_args()
    if not 1<=args.max_items<=1000:
        parser.error('max-items must be between 1 and 1000')
    if settings.app_env.lower()=='production':
        check_schema_revision()
    processed=0
    for _ in range(args.max_items):
        with SessionLocal() as db:
            if not run_one(db):
                break
        processed+=1
        time.sleep(1)
    print(f'Processed attempts: {processed}')


if __name__=='__main__':
    main()
