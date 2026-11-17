"""Owner-only provisioning. Never accepts commercial cookies as credentials."""
from typing import Literal
import re
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from app.core.security import auth_enabled, current_session, password_hash
from app.api.routes_commercial_auth import _origin
from app.core.account_access import revoke_user_sessions
from app.db.database import SessionLocal
from app.db.models import Organization, AccountUser, Membership, AccountSession, AuditLog
import hmac

router = APIRouter(prefix='/api/owner/commercial', tags=['Owner provisioning'])


def guard(request, db, write=False):
    if not auth_enabled():
        raise HTTPException(403, 'Autenticação do proprietário obrigatória.')
    session = current_session(request, db)
    if not session:
        raise HTTPException(401, 'Acesso do proprietário obrigatório.')
    if write:
        _origin(request)
        if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), session.csrf_token):
            raise HTTPException(403, 'CSRF inválido.')


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Provision(Input):
    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{1,79}$')
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=14, max_length=1024)


class MemberIn(Input):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=14, max_length=1024)
    role: Literal['admin', 'member', 'viewer'] = 'member'


class Active(Input):
    active: bool


def _user(db, email, password):
    email = email.strip().casefold()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or not password.strip():
        raise HTTPException(422, 'Credenciais inválidas.')
    if db.scalar(select(AccountUser.id).where(AccountUser.email == email)) is not None:
        raise HTTPException(409, 'Conta já existente; não será sobrescrita.')
    user = AccountUser(email=email, password_hash=password_hash(password), active=True)
    db.add(user)
    db.flush()
    return user


def _commit(db):
    db.commit()


@router.get('/organizations')
def list_organizations(request: Request, limit: int = Query(100, ge=1, le=250), offset: int = Query(0, ge=0)):
    with SessionLocal() as db:
        guard(request, db)
        return [dict(id=o.id, name=o.name, slug=o.slug, active=o.active)
                for o in db.scalars(select(Organization).order_by(Organization.id).offset(offset).limit(limit))]


@router.post('/organizations', status_code=201)
def provision(request: Request, payload: Provision):
    with SessionLocal() as db:
        guard(request, db, True)
        if not payload.name.strip():
            raise HTTPException(422, 'Nome obrigatório.')
        try:
            org = Organization(name=payload.name.strip(), slug=payload.slug, active=True)
            db.add(org)
            db.flush()
            user = _user(db, payload.email, payload.password)
            db.add(Membership(user_id=user.id, organization_id=org.id, role='admin', active=True))
            db.add(AuditLog(event='commercial_provisioned', entity_type='organization', entity_id=org.id,
                            details={'user_id': user.id}))
        except IntegrityError as exc:
            raise HTTPException(409, 'Organização ou conta já existente.') from exc
        result = dict(id=org.id, slug=org.slug, user_id=user.id, active=True)
        try:
            _commit(db)
        except IntegrityError as exc:
            raise HTTPException(409, 'Organização ou conta já existente.') from exc
        return result


@router.get('/organizations/{organization_id}/members')
def members(request: Request, organization_id: int, limit: int = Query(100, ge=1, le=250), offset: int = Query(0, ge=0)):
    with SessionLocal() as db:
        guard(request, db)
        if not db.get(Organization, organization_id):
            raise HTTPException(404, 'Organização não encontrada.')
        rows = db.execute(select(Membership, AccountUser).join(AccountUser, AccountUser.id == Membership.user_id)
                          .where(Membership.organization_id == organization_id)
                          .order_by(Membership.user_id).offset(offset).limit(limit))
        return [dict(user_id=u.id, email=u.email, role=m.role, active=m.active and u.active) for m,u in rows]


@router.post('/organizations/{organization_id}/members', status_code=201)
def add_member(request: Request, organization_id: int, payload: MemberIn):
    with SessionLocal() as db:
        guard(request, db, True)
        if not db.get(Organization, organization_id):
            raise HTTPException(404, 'Organização não encontrada.')
        try:
            user = _user(db, payload.email, payload.password)
            db.add(Membership(user_id=user.id, organization_id=organization_id, role=payload.role, active=True))
            db.add(AuditLog(event='commercial_member_added', entity_type='organization',
                            entity_id=organization_id, details={'user_id':user.id,'role':payload.role}))
            result = dict(user_id=user.id, role=payload.role)
            db.commit()
        except IntegrityError as exc:
            raise HTTPException(409, 'Conta já existente.') from exc
        return result


@router.patch('/organizations/{organization_id}')
def set_active(request: Request, organization_id: int, payload: Active):
    with SessionLocal() as db:
        guard(request, db, True)
        org = db.get(Organization, organization_id)
        if not org:
            raise HTTPException(404, 'Organização não encontrada.')
        org.active = payload.active
        if not payload.active:
            db.execute(delete(AccountSession).where(AccountSession.organization_id == organization_id))
        db.add(AuditLog(event='commercial_org_status', entity_type='organization', entity_id=organization_id,
                        details={'active':payload.active}))
        db.commit()
        return {'active':payload.active}


from app.db.models import CommercialPlan


class PlanIn(Input):
    code: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{1,79}$')
    name: str = Field(min_length=1, max_length=160)
    monthly_price_cents: int = Field(strict=True, ge=0, le=100000000)
    max_members: int = Field(strict=True, ge=1, le=1000000)
    max_leads: int = Field(strict=True, ge=0, le=1000000)
    max_contacts: int = Field(strict=True, ge=0, le=1000000)
    max_tasks: int = Field(strict=True, ge=0, le=1000000)
    max_portfolios: int = Field(strict=True, ge=0, le=1000000)
    max_titles: int = Field(strict=True, ge=0, le=1000000)


def plan_data(row):
    return dict(id=row.id, code=row.code, name=row.name, currency='BRL',
                monthly_price_cents=row.monthly_price_cents, active=row.active,
                **{key:getattr(row,key) for key in ('max_members','max_leads','max_contacts',
                                                    'max_tasks','max_portfolios','max_titles')})


@router.get('/plans')
def list_plans(request: Request, limit: int = Query(100,ge=1,le=250), offset: int = Query(0,ge=0)):
    with SessionLocal() as db:
        guard(request,db)
        return [plan_data(row) for row in db.scalars(select(CommercialPlan)
                .order_by(CommercialPlan.id.desc()).offset(offset).limit(limit))]


@router.post('/plans',status_code=201)
def create_plan(request: Request,payload: PlanIn):
    with SessionLocal() as db:
        guard(request,db,True)
        if not payload.name.strip():
            raise HTTPException(422,'Nome obrigatório.')
        row=CommercialPlan(**(payload.model_dump() | {'name':payload.name.strip()}), active=False)
        db.add(row)
        try:
            db.flush()
            db.add(AuditLog(event='commercial_plan_created',entity_type='commercial_plan',
                            entity_id=row.id,details=plan_data(row)))
            result=plan_data(row)
            db.commit()
        except IntegrityError as exc:
            raise HTTPException(409,'Código do plano já existente.') from exc
        return result


@router.patch('/plans/{plan_id}')
def set_plan_active(request: Request,plan_id: int,payload: Active):
    with SessionLocal() as db:
        guard(request,db,True)
        row=db.get(CommercialPlan,plan_id)
        if row is None:
            raise HTTPException(404,'Plano não encontrado.')
        row.active=payload.active
        db.add(AuditLog(event='commercial_plan_status',entity_type='commercial_plan',
                        entity_id=row.id,details={'active':row.active}))
        result=plan_data(row)
        db.commit()
        return result


from datetime import datetime, timezone
from pydantic import AwareDatetime
from app.db.models import CommercialSubscription
from app.services.commercial_subscriptions import describe


class SubscriptionIn(Input):
    plan_id: int = Field(gt=0, strict=True)
    starts_at: AwareDatetime
    ends_at: AwareDatetime


@router.get('/organizations/{organization_id}/subscription')
def get_subscription(request: Request, organization_id: int):
    with SessionLocal() as db:
        guard(request,db)
        if not db.get(Organization,organization_id):
            raise HTTPException(404,'Organização não encontrada.')
        return describe(db,organization_id)


@router.put('/organizations/{organization_id}/subscription')
def assign_subscription(request: Request, organization_id: int, payload: SubscriptionIn):
    with SessionLocal() as db:
        guard(request,db,True)
        org=db.scalar(select(Organization).where(Organization.id==organization_id).with_for_update())
        if not org:
            raise HTTPException(404,'Organização não encontrada.')
        plan=db.get(CommercialPlan,payload.plan_id)
        if not plan or not plan.active:
            raise HTTPException(422,'Selecione um plano ativo.')
        now=datetime.now(timezone.utc)
        if payload.ends_at <= payload.starts_at or payload.ends_at <= now:
            raise HTTPException(422,'Vigência inválida.')
        previous=describe(db,organization_id)
        row=db.get(CommercialSubscription,organization_id)
        if row is None:
            row=CommercialSubscription(organization_id=organization_id)
            db.add(row)
        row.plan_id=plan.id
        row.starts_at=payload.starts_at.astimezone(timezone.utc)
        row.ends_at=payload.ends_at.astimezone(timezone.utc)
        row.status='active'
        row.updated_at=now
        try:
            db.flush()
            result=describe(db,organization_id)
            db.add(AuditLog(event='commercial_subscription_assigned',entity_type='organization',
                entity_id=organization_id,details={'previous_status':previous['status'],
                'previous_plan_id':previous['plan']['id'] if previous['plan'] else None,
                'previous_starts_at':previous['starts_at'].isoformat() if 'starts_at' in previous else None,
                'previous_ends_at':previous['ends_at'].isoformat() if 'ends_at' in previous else None,
                'plan_id':plan.id,'starts_at':row.starts_at.isoformat(),'ends_at':row.ends_at.isoformat()}))
            db.commit()
        except IntegrityError as exc:
            raise HTTPException(409,'Conflito de assinatura.') from exc
        return result


@router.post('/organizations/{organization_id}/subscription/cancel')
def cancel_subscription(request: Request, organization_id: int):
    with SessionLocal() as db:
        guard(request,db,True)
        org=db.scalar(select(Organization).where(Organization.id==organization_id).with_for_update())
        row=db.get(CommercialSubscription,organization_id) if org else None
        if row is None:
            raise HTTPException(404,'Assinatura não encontrada.')
        if row.status!='cancelled':
            row.status='cancelled'
            row.updated_at=datetime.now(timezone.utc)
            db.add(AuditLog(event='commercial_subscription_cancelled',entity_type='organization',
                            entity_id=organization_id,details={'plan_id':row.plan_id}))
        result=describe(db,organization_id)
        db.commit()
        return result
