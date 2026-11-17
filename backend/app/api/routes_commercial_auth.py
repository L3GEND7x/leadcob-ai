"""Opt-in commercial authentication, isolated from the legacy owner."""
import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.account_access import AccessDenied, authorize, issue_session, revoke_session
from app.core.config import settings
from app.core.security import auth_enabled, stamp
from app.db.database import SessionLocal
from app.db.models import AccountSession, LoginAttempt

router = APIRouter(prefix='/api/commercial/auth', tags=['Commercial access'])
COOKIE = 'leadcob_commercial_session'
COOKIE_PATH = '/api/commercial'


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)
    organization_id: int = Field(gt=0)


class Scope(BaseModel):
    organization_id: int = Field(gt=0)


def _enabled():
    if not settings.commercial_auth_enabled or not auth_enabled():
        raise HTTPException(404, 'Recurso indisponível.')


def _origin(request):
    expected = settings.public_url.rstrip('/') or str(request.base_url).rstrip('/')
    if request.headers.get('origin') != expected:
        raise HTTPException(403, 'Origem não permitida.')


def _reserve_attempt(db, key, now, limit):
    """Atomic conditional update, including concurrent attempts."""
    cutoff = now - timedelta(minutes=15)
    try:
        with db.begin_nested():
            db.add(LoginAttempt(key=key, count=0, started_at=now))
            db.flush()
    except IntegrityError:
        pass
    db.execute(update(LoginAttempt).where(LoginAttempt.key == key,
               LoginAttempt.started_at <= cutoff).values(count=0, started_at=now))
    result = db.execute(update(LoginAttempt).where(LoginAttempt.key == key,
                        LoginAttempt.count < limit).values(count=LoginAttempt.count + 1))
    return result.rowcount == 1


@router.post('/login')
def login(payload: Login, request: Request):
    _enabled()
    _origin(request)
    now = datetime.now(timezone.utc)
    peer = request.client.host if request.client else 'unknown'
    email = payload.email.strip().casefold()
    with SessionLocal() as db:
        peer_key = 'commercial-peer:' + hashlib.sha256(peer.encode()).hexdigest()
        account_key = 'commercial-account:' + hashlib.sha256((peer + '\0' + email).encode()).hexdigest()
        permitted = _reserve_attempt(db, peer_key, now, 30)
        if permitted:
            permitted = _reserve_attempt(db, account_key, now, 5)
        db.commit()
        if not permitted:
            raise HTTPException(429, 'Muitas tentativas. Aguarde 15 minutos.')
        try:
            raw, csrf = issue_session(db, email, payload.password, payload.organization_id)
        except AccessDenied:
            raise HTTPException(401, 'Credenciais inválidas.')
        principal = authorize(db, raw, payload.organization_id, 'read')
        db.query(AccountSession).filter(AccountSession.expires_at <= now).delete(synchronize_session=False)
        db.commit()
    response = JSONResponse(dict(authenticated=True, organization_id=principal.organization_id,
                                 role=principal.role, csrf_token=csrf))
    response.set_cookie(COOKIE, raw, httponly=True, secure=settings.app_env == 'production',
                        samesite='strict', max_age=28800, path=COOKIE_PATH)
    return response


@router.get('/session')
def session(request: Request, organization_id: int):
    _enabled()
    raw = request.cookies.get(COOKIE, '')
    with SessionLocal() as db:
        try:
            principal = authorize(db, raw, organization_id, 'read')
        except AccessDenied:
            return {'authenticated': False}
        row = db.get(AccountSession, hashlib.sha256(raw.encode()).hexdigest())
        if row is None:
            return {'authenticated': False}
        return dict(authenticated=True, organization_id=principal.organization_id,
                    role=principal.role, csrf_token=row.csrf_token)


@router.post('/logout')
def logout(payload: Scope, request: Request):
    _enabled()
    _origin(request)
    raw = request.cookies.get(COOKIE, '')
    with SessionLocal() as db:
        try:
            authorize(db, raw, payload.organization_id, 'read')
        except AccessDenied:
            raise HTTPException(401, 'Sessão inválida.')
        row = db.get(AccountSession, hashlib.sha256(raw.encode()).hexdigest())
        import hmac
        if row is None or not hmac.compare_digest(request.headers.get('x-csrf-token', '').encode('utf-8'), row.csrf_token.encode('utf-8')):
            raise HTTPException(403, 'CSRF inválido.')
        revoke_session(db, raw)
        db.commit()
    response = JSONResponse({'ok': True})
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
    return response
