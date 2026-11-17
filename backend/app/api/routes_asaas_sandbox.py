"""Authenticated sandbox inbox. Never trusts webhook claims as payment proof."""
import hmac
import json
import re
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.db.database import SessionLocal

router = APIRouter()
PATH = "/api/webhooks/asaas/sandbox"
MAX_BODY = 65536


def authenticated(secret, supplied):
    return (len(secret) >= 32 and bool(supplied) and
            hmac.compare_digest(secret.encode("utf-8"), supplied.encode("utf-8")))


def parse_event(raw):
    try:
        body = json.loads(raw)
        event_id, event_type, payment_id = body["id"], body["event"], body["payment"]["id"]
        if not all(isinstance(v, str) for v in (event_id, event_type, payment_id)):
            raise ValueError
        if not (re.fullmatch(r"evt_[A-Za-z0-9_-]{1,150}", event_id)
                and re.fullmatch(r"PAYMENT_[A-Z0-9_]{1,70}", event_type)
                and re.fullmatch(r"pay_[A-Za-z0-9_-]{1,100}", payment_id)):
            raise ValueError
        return event_id, event_type, payment_id
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise HTTPException(422, "Evento sandbox inválido.") from exc


def store_event(event_id, event_type, payment_id):
    with SessionLocal() as db:
        try:
            db.execute(text("""INSERT INTO asaas_sandbox_events
                (event_id,event_type,payment_id,received_at) VALUES (:id,:kind,:pid,:now)"""),
                {"id": event_id, "kind": event_type, "pid": payment_id,
                 "now": datetime.now(timezone.utc)})
            db.commit()
            return {"accepted": True, "duplicate": False}
        except IntegrityError as exc:
            db.rollback()
            previous = db.execute(text("SELECT event_type,payment_id FROM asaas_sandbox_events WHERE event_id=:id"),
                                  {"id": event_id}).mappings().one_or_none()
            if previous is None or previous["event_type"] != event_type or previous["payment_id"] != payment_id:
                raise HTTPException(409, "Identificador de evento em conflito.") from exc
            return {"accepted": True, "duplicate": True}


@router.post(PATH, include_in_schema=False)
async def receive_event(request: Request):
    if not authenticated(settings.asaas_sandbox_webhook_token, request.headers.get("asaas-access-token", "")):
        raise HTTPException(401, "Webhook não autorizado.")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_BODY:
            raise HTTPException(413, "Evento excede o limite.")
        raw.extend(chunk)
    event = parse_event(raw)
    return await run_in_threadpool(store_event, *event)
