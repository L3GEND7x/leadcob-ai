from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import ContactDiscoveryItem
from app.services.contact_discovery_queue import enqueue, progress, claim, finish, run_one


def test_queue_lifecycle(monkeypatch):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        job = enqueue(db, [10, 10, 20, 30])
        assert progress(db, job)['queued'] == 3
        item, company, token = claim(db, now)
        assert company == 10
        assert progress(db, job)['running'] == 1
        renewed = claim(db, now + timedelta(minutes=6))
        assert renewed[:2] == (item, company)
        assert renewed[2] != token
        assert not finish(db, item, token, {'status':'completed'})
        assert finish(db, item, renewed[2], {'status':'completed','added':2})
        item, company, token = claim(db, now)
        assert company == 20
        assert finish(db, item, token, {'status':'suppressed'})
        for _ in range(3):
            item, company, token = claim(db, now)
            assert company == 30
            assert finish(db, item, token, {'status':'unavailable'})
        assert claim(db, now) is None
        assert progress(db,job) == dict(job_id=job,total=3,queued=0,running=0,completed=1,failed=1,skipped=1)
        another=enqueue(db,[40])
        from app.api import routes_contacts
        monkeypatch.setattr(routes_contacts,'discover_batch',lambda payload, db: {'items':[{'status':'completed','added':1}]})
        assert run_one(db)
        assert progress(db,another)['completed']==1
        assert not run_one(db)
    engine.dispose()


def test_diagnostics_and_unrecoverable_rows():
    from app.services.contact_discovery_queue import diagnostics
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    now=datetime.now(timezone.utc)
    with Session(engine) as db:
        job=enqueue(db,[10,20,30])
        rows=db.query(ContactDiscoveryItem).filter_by(job_id=job).order_by(ContactDiscoveryItem.id).all()
        rows[0].status='running'
        rows[0].attempts=1
        rows[1].attempts=3
        rows[2].status='running'
        rows[2].attempts=3
        rows[2].claim_token='expired'
        rows[2].lease_until=now-timedelta(minutes=1)
        db.commit()
        before=diagnostics(db,now)
        assert before['missing_claim_metadata']==1
        assert before['expired_leases']==1
        assert before['exhausted_queued']==1
        assert before['worker_verified'] is False
        assert before['oldest_queued_job_at'] is not None
        assert claim(db,now) is None
        after=diagnostics(db,now)
        assert after['counts']['failed']==3
        assert after['missing_claim_metadata']==after['expired_leases']==after['exhausted_queued']==0
        assert after['oldest_queued_job_at'] is None
    engine.dispose()


def test_worker_heartbeat_fresh_stopped_and_expired():
    from app.services.contact_discovery_queue import diagnostics, record_heartbeat
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    now=datetime.now(timezone.utc)
    with Session(engine) as db:
        assert diagnostics(db,now)['worker_verified'] is False
        record_heartbeat(db,'worker-a','idle',0,now)
        assert diagnostics(db,now)['worker_verified'] is True
        assert diagnostics(db,now)['recent_workers']==1
        assert diagnostics(db,now+timedelta(minutes=8))['worker_verified'] is False
        record_heartbeat(db,'worker-a','stopped',1,now+timedelta(seconds=1))
        result=diagnostics(db,now+timedelta(seconds=2))
        assert result['worker_verified'] is False
        assert result['worker_states']['stopped']==1
        record_heartbeat(db,'worker-b','processing',0,now)
        assert diagnostics(db,now+timedelta(seconds=2))['recent_workers']==1
    engine.dispose()
