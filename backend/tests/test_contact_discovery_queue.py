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
