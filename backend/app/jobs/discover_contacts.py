"""Explicitly launched enrichment worker; no automatic messaging."""
import argparse
import logging
import signal
import threading
import json
from uuid import uuid4
from app.db.database import SessionLocal, check_schema_revision
from app.services.contact_discovery_queue import run_one, record_heartbeat, diagnostics, prune_heartbeats
from app.core.config import settings

logger = logging.getLogger(__name__)


def process(stop, max_items=20, continuous=False, idle_seconds=15, interval_seconds=2,
            session_factory=None, process_one=None, heartbeat=None):
    session_factory = session_factory or SessionLocal
    process_one = process_one or run_one
    processed = 0
    while not stop.is_set() and (continuous or processed < max_items):
        try:
            if heartbeat:
                heartbeat('processing',processed)
            with session_factory() as db:
                worked = process_one(db)
        except Exception:
            logger.error('Discovery worker iteration failed; will stop or retry after idle interval.')
            if heartbeat:
                heartbeat('error',processed)
            if not continuous:
                raise
            stop.wait(idle_seconds)
            continue
        if worked:
            processed += 1
            if heartbeat:
                heartbeat('idle',processed)
            stop.wait(interval_seconds)
        elif continuous:
            if heartbeat:
                heartbeat('idle',processed)
            stop.wait(idle_seconds)
        else:
            break
    return processed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-items', type=int, default=20)
    parser.add_argument('--continuous', action='store_true')
    parser.add_argument('--probe', action='store_true', help='Read-only queue metrics; no external requests or job claims')
    parser.add_argument('--idle-seconds', type=int, default=15)
    parser.add_argument('--interval-seconds', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.max_items <= 1000:
        parser.error('max-items must be between 1 and 1000')
    if not 5 <= args.idle_seconds <= 300 or not 1 <= args.interval_seconds <= 60:
        parser.error('invalid idle or processing interval')
    logging.basicConfig(level=logging.INFO)
    if settings.app_env.strip().lower() == 'production':
        check_schema_revision()
    if args.probe:
        with SessionLocal() as db:
            report = diagnostics(db)
        print(json.dumps({
            'counts': report['counts'], 'expired_leases': report['expired_leases'],
            'worker_verified': report['worker_verified'], 'recent_workers': report['recent_workers'],
            'collection_attempted': False
        }, ensure_ascii=False))
        return
    if not settings.contact_discovery_worker_enabled:
        logger.warning('Worker desativado: CONTACT_DISCOVERY_WORKER_ENABLED deve ser true.')
        return
    with SessionLocal() as db:
        prune_heartbeats(db)
    stop = threading.Event()
    def halt(signum, frame):
        stop.set()
    signal.signal(signal.SIGTERM, halt)
    signal.signal(signal.SIGINT, halt)
    worker_id=str(uuid4())
    last_attempts=0
    def heartbeat(state, attempts):
        nonlocal last_attempts
        last_attempts=attempts
        with SessionLocal() as db:
            record_heartbeat(db,worker_id,state,attempts)
    heartbeat('starting',0)
    try:
        processed = process(stop, args.max_items, args.continuous,
                            args.idle_seconds, args.interval_seconds,heartbeat=heartbeat)
        logger.info('Processed attempts: %s', processed)
    finally:
        try:
            heartbeat('stopped',last_attempts)
        except Exception:
            logger.error('Unable to record worker shutdown.')


if __name__ == '__main__':
    main()
