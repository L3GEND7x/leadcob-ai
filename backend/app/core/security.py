"""Single-owner authentication. A deployment is one private workspace."""
import hashlib
import hmac
import secrets
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models import LoginSession, LoginAttempt, AuditLog

actor = ContextVar('audit_actor', default='local-owner')
router = APIRouter(prefix='/api/auth', tags=['Acesso'])
COOKIE = 'leadcob_session'


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    return f'pbkdf2_sha256.{salt}.{digest}'


def password_matches(password):
    try:
        algorithm, salt, digest = settings.admin_password_hash.split('.')
        return algorithm == 'pbkdf2_sha256' and hmac.compare_digest(password_hash(password, salt), settings.admin_password_hash)
    except ValueError:
        return False


def auth_enabled():
    return bool(settings.admin_password_hash) or settings.app_env == 'production'


def validate_configuration():
    if settings.app_env == 'production':
        if not settings.admin_password_hash.startswith('pbkdf2_sha256.'):
            raise RuntimeError('Produção exige ADMIN_PASSWORD_HASH. Execute python -m app.core.security.')
        if not settings.public_url.startswith('https://'):
            raise RuntimeError('Produção exige PUBLIC_URL HTTPS.')
        if settings.demo_seed:
            raise RuntimeError('DEMO_SEED deve estar desativado em produção.')


def stamp(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def current_session(request, db):
    raw = request.cookies.get(COOKIE, '')
    session = db.get(LoginSession, hashlib.sha256(raw.encode()).hexdigest()) if raw else None
    if session and stamp(session.expires_at) > datetime.now(timezone.utc):
        return session
    return None


async def access_middleware(request, call_next):
    public = request.url.path in {'/', '/api/health', '/api/auth/login', '/api/auth/session'} or request.url.path.startswith('/static/')
    token = actor.set('local-owner')
    try:
        if auth_enabled():
            with SessionLocal() as db:
                session = current_session(request, db)
                if not public and not session:
                    return JSONResponse({'detail': 'Entre para acessar o painel.'}, status_code=401)
                if session:
                    request.state.user = session.username
                    actor.set(session.username)
                if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
                    origin = request.headers.get('origin')
                    expected = settings.public_url.rstrip('/') or str(request.base_url).rstrip('/')
                    if origin and origin != expected:
                        return JSONResponse({'detail': 'Origem não permitida.'}, status_code=403)
                    if request.url.path != '/api/auth/login' and (not session or not hmac.compare_digest(request.headers.get('x-csrf-token', ''), session.csrf_token)):
                        return JSONResponse({'detail': 'Atualize a sessão antes de gravar.'}, status_code=403)
        else:
            host = request.client.host if request.client else ''
            if host not in {'127.0.0.1', '::1', 'testclient'}:
                return JSONResponse({'detail': 'Configure autenticação para acesso pela rede.'}, status_code=403)
            request.state.user = 'local-owner'
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response
    finally:
        actor.reset(token)


class Credentials(BaseModel):
    username: str = Field(max_length=120)
    password: str = Field(max_length=1024)


@router.post('/login')
def login(payload: Credentials, request: Request):
    if not auth_enabled():
        raise HTTPException(400, 'Acesso local ativo; configure autenticação para publicar.')
    now = datetime.now(timezone.utc)
    # Shared database counter works across API processes. The account counter also
    # prevents spreading attempts over IPs. Reset only after the lock window.
    with SessionLocal() as db:
        key = 'owner'
        attempt = db.get(LoginAttempt, key)
        if attempt and stamp(attempt.started_at) < now - timedelta(minutes=15):
            attempt.count = 0
            attempt.started_at = now
        if attempt and attempt.count >= 5:
            raise HTTPException(429, 'Muitas tentativas. Aguarde 15 minutos.')
        if not attempt:
            attempt = LoginAttempt(key=key, count=0, started_at=now)
            db.add(attempt)
        attempt.count += 1
        db.commit()
        valid = password_matches(payload.password)
        if not valid or not hmac.compare_digest(payload.username, settings.admin_username):
            raise HTTPException(401, 'Credenciais inválidas.')
        attempt.count = 0
        raw, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
        db.add(LoginSession(token_hash=hashlib.sha256(raw.encode()).hexdigest(), csrf_token=csrf,
                            username=settings.admin_username, expires_at=now + timedelta(hours=8)))
        db.query(LoginSession).filter(LoginSession.expires_at < now).delete()
        db.commit()
    response = JSONResponse({'authenticated': True, 'username': settings.admin_username, 'csrf_token': csrf})
    response.set_cookie(COOKIE, raw, httponly=True, secure=settings.app_env == 'production', samesite='strict', max_age=28800)
    return response


@router.get('/session')
def session_info(request: Request):
    if not auth_enabled():
        return {'authenticated': True, 'username': 'local-owner', 'csrf_token': '', 'mode': 'local'}
    with SessionLocal() as db:
        session = current_session(request, db)
        return {'authenticated': bool(session), 'username': session.username if session else None,
                'csrf_token': session.csrf_token if session else '', 'mode': 'cloud'}


@router.post('/logout')
def logout(request: Request):
    with SessionLocal() as db:
        session = current_session(request, db)
        if session:
            db.delete(session)
            db.commit()
    response = JSONResponse({'ok': True})
    response.delete_cookie(COOKIE)
    return response


@event.listens_for(Session, 'before_flush')
def identify_audit_actor(session, flush_context, instances):
    for item in session.new:
        if isinstance(item, AuditLog):
            item.details = {**(item.details or {}), 'actor': actor.get()}


if __name__ == '__main__':
    import getpass
    password = getpass.getpass('Senha do proprietário (mínimo 14 caracteres): ')
    if len(password) < 14:
        raise SystemExit('Use pelo menos 14 caracteres.')
    print(password_hash(password))
