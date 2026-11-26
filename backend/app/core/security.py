"""Single-owner authentication. A deployment is one private workspace."""
import hashlib
import hmac
import secrets
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.client_ip import client_ip
from app.db.database import SessionLocal
from app.db.models import LoginSession, LoginAttempt, AuditLog

actor = ContextVar('audit_actor', default='local-owner')
router = APIRouter(prefix='/api/auth', tags=['Acesso'])
COOKIE = 'leadcob_session'
# A interface usa atributos onclick e estilos inline, por isso 'unsafe-inline' em script/style.
# Mesmo assim a política bloqueia scripts de outros domínios, envio de dados para fora (connect-src),
# formulários para outros sites, <base> e <object>, e o carregamento do painel dentro de outro site.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)


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
    return bool(settings.admin_password_hash) or settings.app_env.strip().lower() == 'production'


def validate_configuration():
    if settings.app_env.strip().lower() == 'production':
        parts = settings.admin_password_hash.split('.')
        if len(parts) != 3 or parts[0] != 'pbkdf2_sha256' or len(parts[1]) != 32 or len(parts[2]) != 64:
            raise RuntimeError('Produção exige ADMIN_PASSWORD_HASH. Execute python -m app.core.security.')
        parsed = urlparse(settings.public_url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
            raise RuntimeError('Produção exige PUBLIC_URL HTTPS.')
        from app.db.database import normalized_database_url
        db_url = make_url(normalized_database_url())
        if (db_url.get_backend_name() != 'postgresql' or not db_url.host or
                not db_url.username or not db_url.password):
            raise RuntimeError('Produção exige conexão PostgreSQL autenticada.')
        if settings.demo_seed:
            raise RuntimeError('DEMO_SEED deve estar desativado em produção.')
        if settings.commercial_auth_enabled and not settings.commercial_entitlements_enabled:
            raise RuntimeError('Acesso comercial exige limites de assinatura ativos em produção.')
        if settings.workspace_assistant_enabled or settings.workspace_registry_search_enabled:
            if not (settings.commercial_auth_enabled and settings.commercial_entitlements_enabled):
                raise RuntimeError('Recursos experimentais exigem autenticação e limites comerciais em produção.')
        if settings.workspace_assistant_enabled:
            from math import isfinite
            if not settings.openai_api_key.strip() or not settings.openai_model.strip() or not all(
                    isfinite(v) and 0 < v <= 1000 for v in (
                        settings.workspace_assistant_monthly_budget_usd,
                        settings.openai_input_usd_per_million,
                        settings.openai_output_usd_per_million)):
                raise RuntimeError('IA comercial exige modelo, chave, preços e orçamento explícitos.')


def stamp(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def session_key(raw):
    """Chave da sessão no banco. Inclui o usuário e o hash da senha configurados: trocar ADMIN_PASSWORD_HASH
    (ou ADMIN_USERNAME) encerra todas as sessões abertas antes da troca, sem migração de banco."""
    material = '\0'.join([raw, settings.admin_username, settings.admin_password_hash])
    return hashlib.sha256(material.encode()).hexdigest()


def current_session(request, db):
    raw = request.cookies.get(COOKIE, '')
    session = db.get(LoginSession, session_key(raw)) if raw else None
    if session and stamp(session.expires_at) > datetime.now(timezone.utc):
        return session
    return None


async def access_middleware(request, call_next):
    public = request.url.path in {'/', '/favicon.ico', '/api/health', '/api/auth/login', '/api/auth/session'} or request.url.path.startswith('/static/')
    token = actor.set('local-owner')
    try:
        if request.method == 'POST' and request.url.path == '/api/webhooks/asaas/sandbox':
            # Exact webhook route authenticates independently of browser sessions.
            actor.set('asaas-sandbox-webhook')
        elif request.url.path in {'/commercial', '/api/commercial/auth/login', '/api/commercial/auth/session', '/api/commercial/auth/logout'} or request.url.path.startswith('/api/commercial/workspace/'):
            # Only this dedicated namespace and the exact auth routes use commercial credentials.
            # Each handler enforces the feature flag, authorization and origin policy.
            pass
        elif auth_enabled():
            with SessionLocal() as db:
                session = current_session(request, db)
                if not public and not session:
                    # Only browser navigation to these two exact HTML pages
                    # redirects. API clients retain 401, including release smoke.
                    owner_pages = {'/owner/discovery': 'discovery', '/owner/commercial': 'commercial'}
                    destination = owner_pages.get(request.url.path)
                    html_navigation = (request.headers.get('sec-fetch-mode') == 'navigate'
                                       or request.headers.get('accept', '').split(',')[0].strip().lower() == 'text/html')
                    if request.method in {'GET', 'HEAD'} and destination and html_navigation:
                        return RedirectResponse('/?next=' + destination, status_code=303,
                                                headers={'Cache-Control': 'no-store',
                                                         'X-Content-Type-Options': 'nosniff',
                                                         'Referrer-Policy': 'same-origin'})
                    return JSONResponse({'detail': 'Entre para acessar o painel.'}, status_code=401)
                if session:
                    request.state.user = session.username
                    actor.set(session.username)
                if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
                    origin = request.headers.get('origin')
                    expected = settings.public_url.rstrip('/') or str(request.base_url).rstrip('/')
                    if origin and origin != expected:
                        return JSONResponse({'detail': 'Origem não permitida.'}, status_code=403)
                    if request.url.path != '/api/auth/login' and (not session or not hmac.compare_digest(request.headers.get('x-csrf-token', '').encode('utf-8'), session.csrf_token.encode('utf-8'))):
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
        response.headers['Content-Security-Policy'] = CONTENT_SECURITY_POLICY
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=(), payment=()'
        if settings.app_env.strip().lower() == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
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
    # Partition attempts by submitted account and transport peer; do not trust arbitrary forwarded headers.
    # This is a first layer, not a substitute for a trusted edge rate limiter.
    with SessionLocal() as db:
        peer = client_ip(request)
        key = 'login:' + hashlib.sha256((peer + '\0' + payload.username.casefold()).encode()).hexdigest()
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
        if not valid or not hmac.compare_digest(payload.username.encode('utf-8'), settings.admin_username.encode('utf-8')):
            raise HTTPException(401, 'Credenciais inválidas.')
        attempt.count = 0
        raw, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
        db.add(LoginSession(token_hash=session_key(raw), csrf_token=csrf,
                            username=settings.admin_username, expires_at=now + timedelta(hours=8)))
        db.query(LoginSession).filter(LoginSession.expires_at < now).delete(synchronize_session=False)
        db.query(LoginAttempt).filter(LoginAttempt.started_at < now - timedelta(days=1)).delete(synchronize_session=False)
        db.commit()
    response = JSONResponse({'authenticated': True, 'username': settings.admin_username, 'csrf_token': csrf})
    response.set_cookie(COOKIE, raw, httponly=True, secure=settings.app_env.strip().lower() == 'production', samesite='strict', max_age=28800)
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
