"""Owner queue. One item per worker iteration, no automatic messages."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import select, update, or_, and_, func
from app.db.models import ContactDiscoveryJob as Job, ContactDiscoveryItem as Item, ContactWorkerHeartbeat
from app.core.security import stamp

MAX_ATTEMPTS = 3
LEASE = timedelta(minutes=5)


def enqueue(db, company_ids):
    ids = list(dict.fromkeys(company_ids))
    if not 1 <= len(ids) <= 1000 or any(type(i) is not int or i <= 0 for i in ids):
        raise ValueError('Invalid company list')
    job = Job()
    db.add(job)
    db.flush()
    db.add_all([Item(job_id=job.id, company_id=i, status='queued', attempts=0, result={}) for i in ids])
    db.flush()
    job_id = job.id
    db.commit()
    return job_id


def progress(db, job_id):
    if not db.get(Job, job_id):
        return None
    counts = dict(db.execute(select(Item.status, func.count(Item.id))
                            .where(Item.job_id == job_id).group_by(Item.status)).all())
    return dict(job_id=job_id, total=sum(counts.values()),
                **{k:counts.get(k,0) for k in ('queued','running','completed','failed','skipped')})


def claim(db, now=None, job_id=None):
    now = now or datetime.now(timezone.utc)
    # Exhausted expired leases become terminal, rather than vanishing forever.
    db.execute(update(Item).where(Item.status=='running', Item.lease_until<=now,
                                  Item.attempts>=MAX_ATTEMPTS).execution_options(synchronize_session=False).values(status='failed',
                                  claim_token=None, lease_until=None, result={'status':'lease_expired'}))
    # Rows without complete claim metadata cannot be safely resumed automatically.
    db.execute(update(Item).where(Item.status=='running',
        or_(Item.lease_until.is_(None),Item.claim_token.is_(None)))
        .execution_options(synchronize_session=False).values(status='failed',claim_token=None,
            lease_until=None,result={'status':'invalid_claim_metadata'}))
    db.execute(update(Item).where(Item.status=='queued',Item.attempts>=MAX_ATTEMPTS)
        .execution_options(synchronize_session=False).values(status='failed',claim_token=None,
            lease_until=None,result={'status':'attempts_exhausted'}))
    eligible = or_(Item.status=='queued', and_(Item.status=='running', Item.lease_until<=now))
    selection = select(Item.id).where(eligible, Item.attempts<MAX_ATTEMPTS)
    if job_id is not None:
        selection = selection.where(Item.job_id == job_id)
    selection = selection.order_by(Item.id).limit(1)
    if db.get_bind().dialect.name == 'postgresql':
        selection = selection.with_for_update(skip_locked=True)
    candidate = db.scalar(selection)
    if candidate is None:
        db.commit()
        return None
    token = str(uuid4())
    changed = db.execute(update(Item).where(Item.id==candidate, eligible, Item.attempts<MAX_ATTEMPTS)
                         .execution_options(synchronize_session=False)
                         .values(status='running', attempts=Item.attempts+1,
                                 claim_token=token, lease_until=now+LEASE))
    if changed.rowcount != 1:
        db.rollback()
        return None
    item = db.get(Item,candidate, populate_existing=True)
    result = (item.id, item.company_id, token)
    db.commit()
    return result


def finish(db, item_id, token, result):
    status = result.get('status')
    item = db.get(Item,item_id,populate_existing=True)
    if item is None or item.status!='running' or item.claim_token!=token:
        db.rollback()
        return False
    if status=='completed':
        target='completed'
    elif status in {'suppressed','not_found','missing_website','invalid_cnpj','changed_or_suppressed'}:
        target='skipped'
    else:
        target='queued' if item.attempts<MAX_ATTEMPTS else 'failed'
    changed = db.execute(update(Item).where(Item.id==item_id, Item.status=='running', Item.claim_token==token)
                         .values(status=target, result=result, claim_token=None, lease_until=None))
    db.commit()
    return changed.rowcount==1


def run_one(db, job_id=None):
    from app.api.routes_contacts import discover_batch, BatchDiscoveryIn
    claimed = claim(db, job_id=job_id)
    if claimed is None:
        return False
    item_id, company_id, token = claimed
    try:
        result = discover_batch(BatchDiscoveryIn(company_ids=[company_id]), db)['items'][0]
    except Exception:
        db.rollback()
        result = {'status':'error','added':0}
    finish(db,item_id,token,result)
    return True


def diagnostics(db, now=None):
    """Read-only queue observations; not an assertion that a worker is alive."""
    now = now or datetime.now(timezone.utc)
    counts = dict(db.execute(select(Item.status, func.count(Item.id)).group_by(Item.status)).all())
    expired = db.scalar(select(func.count(Item.id)).where(Item.status=='running', Item.lease_until<=now)) or 0
    missing_lease = db.scalar(select(func.count(Item.id)).where(Item.status=='running',
        or_(Item.lease_until.is_(None), Item.claim_token.is_(None)))) or 0
    exhausted = db.scalar(select(func.count(Item.id)).where(Item.status=='queued',Item.attempts>=MAX_ATTEMPTS)) or 0
    oldest = db.scalar(select(func.min(Job.created_at)).join(Item,Item.job_id==Job.id).where(Item.status=='queued'))
    recent = list(db.scalars(select(ContactWorkerHeartbeat).where(
        ContactWorkerHeartbeat.observed_at >= now-timedelta(seconds=420),
        ContactWorkerHeartbeat.observed_at <= now).order_by(ContactWorkerHeartbeat.observed_at.desc())))
    active = [x for x in recent if x.state in ('starting','processing','idle')]
    latest = db.scalar(select(ContactWorkerHeartbeat.observed_at).order_by(
        ContactWorkerHeartbeat.observed_at.desc()).limit(1))
    return dict(observed_at=now.isoformat(), counts={k:counts.get(k,0) for k in
        ('queued','running','completed','failed','skipped')}, expired_leases=expired,
        missing_claim_metadata=missing_lease, exhausted_queued=exhausted,
        oldest_queued_job_at=stamp(oldest).isoformat() if oldest else None,
        worker_verified=bool(active), recent_workers=len(active),
        last_worker_observed_at=stamp(latest).isoformat() if latest else None,
        worker_states={state:sum(x.state==state for x in recent) for state in ('starting','processing','idle','error','stopped')},
        note='Atividade recente registrada pelo worker (até 7 minutos), não prova atividade instantânea ou coleta bem-sucedida.')


def record_heartbeat(db, worker_id, state, attempts_processed, now=None):
    now=now or datetime.now(timezone.utc)
    if state not in ('starting','processing','idle','error','stopped'):
        raise ValueError('Invalid worker state')
    row=db.get(ContactWorkerHeartbeat,worker_id)
    if row is None:
        row=ContactWorkerHeartbeat(worker_id=worker_id)
        db.add(row)
    row.observed_at=now
    row.state=state
    row.attempts_processed=attempts_processed
    db.commit()


def prune_heartbeats(db, now=None, retention_days=30):
    """Cap historical worker heartbeat storage without touching pending jobs."""
    from sqlalchemy import delete
    if not 1 <= retention_days <= 365:
        raise ValueError("Invalid retention.")
    now = now or datetime.now(timezone.utc)
    result = db.execute(delete(ContactWorkerHeartbeat).where(
        ContactWorkerHeartbeat.observed_at < now - timedelta(days=retention_days)))
    db.commit()
    return result.rowcount
