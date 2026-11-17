"""Explicitly launched enrichment worker; no automatic messaging."""
import argparse
import logging
import signal
import threading
from app.db.database import SessionLocal, check_schema_revision
from app.services.contact_discovery_queue import run_one
from app.core.config import settings

logger = logging.getLogger(__name__)


def process(stop, max_items=20, continuous=False, idle_seconds=15, interval_seconds=2,
            session_factory=None, process_one=None):
    session_factory = session_factory or SessionLocal
    process_one = process_one or run_one
    processed = 0
    while not stop.is_set() and (continuous or processed < max_items):
        try:
            with session_factory() as db:
                worked = process_one(db)
        except Exception:
            logger.error('Discovery worker iteration failed; will stop or retry after idle interval.')
            if not continuous:
                raise
            stop.wait(idle_seconds)
            continue
        if worked:
            processed += 1
            stop.wait(interval_seconds)
        elif continuous:
            stop.wait(idle_seconds)
        else:
            break
    return processed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-items', type=int, default=20)
    parser.add_argument('--continuous', action='store_true')
    parser.add_argument('--idle-seconds', type=int, default=15)
    parser.add_argument('--interval-seconds', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.max_items <= 1000:
        parser.error('max-items must be between 1 and 1000')
    if not 5 <= args.idle_seconds <= 300 or not 1 <= args.interval_seconds <= 60:
        parser.error('invalid idle or processing interval')
    logging.basicConfig(level=logging.INFO)
    if settings.app_env.lower() == 'production':
        check_schema_revision()
    stop = threading.Event()
    def halt(signum, frame):
        stop.set()
    signal.signal(signal.SIGTERM, halt)
    signal.signal(signal.SIGINT, halt)
    processed = process(stop, args.max_items, args.continuous,
                        args.idle_seconds, args.interval_seconds)
    logger.info('Processed attempts: %s', processed)


if __name__ == '__main__':
    main()
