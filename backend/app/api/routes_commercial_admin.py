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


from datetime import date
from app.db.models import CommercialInvoice
from sqlalchemy import update


class InvoiceIn(Input):
    plan_id: int = Field(gt=0, strict=True)
    period_start: date
    period_end: date
    due_date: date


class SettlementIn(Input):
    amount_cents: int = Field(gt=0, strict=True)
    payment_reference: str = Field(min_length=3,max_length=160)
    paid_at: AwareDatetime


def invoice_data(row):
    return dict(id=row.id, organization_id=row.organization_id, plan_id=row.plan_id,
        period_start=row.period_start, period_end=row.period_end, due_date=row.due_date,
        currency='BRL', amount_cents=row.amount_cents, status=row.status,
        payment_reference=row.payment_reference, paid_at=row.paid_at)


def billing_lock(db, organization_id):
    result=db.execute(update(Organization).where(Organization.id==organization_id)
                      .values(active=Organization.active))
    if result.rowcount!=1:
        raise HTTPException(404,'Organização não encontrada.')


@router.get('/organizations/{organization_id}/invoices')
def list_invoices(request: Request, organization_id: int,
                  limit: int = Query(100,ge=1,le=250), offset: int = Query(0,ge=0)):
    with SessionLocal() as db:
        guard(request,db)
        if not db.get(Organization,organization_id):
            raise HTTPException(404,'Organização não encontrada.')
        return [invoice_data(row) for row in db.scalars(select(CommercialInvoice)
                .where(CommercialInvoice.organization_id==organization_id)
                .order_by(CommercialInvoice.id.desc()).offset(offset).limit(limit))]


@router.post('/organizations/{organization_id}/invoices',status_code=201)
def create_invoice(request: Request, organization_id: int, payload: InvoiceIn):
    with SessionLocal() as db:
        guard(request,db,True)
        billing_lock(db,organization_id)
        if payload.period_end<=payload.period_start:
            raise HTTPException(422,'Período inválido.')
        start,end=payload.period_start.isoformat(),payload.period_end.isoformat()
        existing=db.scalar(select(CommercialInvoice).where(
            CommercialInvoice.organization_id==organization_id,
            CommercialInvoice.period_start==start,CommercialInvoice.period_end==end))
        if existing:
            if existing.plan_id!=payload.plan_id or existing.due_date!=payload.due_date.isoformat():
                raise HTTPException(409,'Período já registrado com outros dados.')
            return invoice_data(existing)
        overlap=db.scalar(select(CommercialInvoice.id).where(
            CommercialInvoice.organization_id==organization_id,
            CommercialInvoice.period_start<end,CommercialInvoice.period_end>start,
            CommercialInvoice.status!='void').limit(1))
        if overlap:
            raise HTTPException(409,'Existe recebível com período sobreposto.')
        plan=db.get(CommercialPlan,payload.plan_id)
        if not plan or not plan.active or plan.monthly_price_cents<=0:
            raise HTTPException(422,'Plano ativo e pago obrigatório.')
        # Only one calendar month, clamped to the last day of a shorter month.
        from calendar import monthrange
        from datetime import date as calendar_date
        y,m=payload.period_start.year,payload.period_start.month
        y,m=(y+1,1) if m==12 else (y,m+1)
        expected=calendar_date(y,m,min(payload.period_start.day,monthrange(y,m)[1]))
        if payload.period_end!=expected:
            raise HTTPException(422,'Informe um período mensal.')
        row=CommercialInvoice(organization_id=organization_id,plan_id=plan.id,
            period_start=start,period_end=end,due_date=payload.due_date.isoformat(),
            amount_cents=plan.monthly_price_cents,status='open')
        db.add(row)
        try:
            db.flush()
            result=invoice_data(row)
            db.add(AuditLog(event='commercial_invoice_created',entity_type='commercial_invoice',
                            entity_id=row.id,details={'organization_id':organization_id,
                            'amount_cents':row.amount_cents,'period_start':start,'period_end':end}))
            db.commit()
        except IntegrityError as exc:
            raise HTTPException(409,'Conflito de recebível.') from exc
        return result


@router.post('/organizations/{organization_id}/invoices/{invoice_id}/settle')
def settle_invoice(request: Request,organization_id: int,invoice_id: int,payload: SettlementIn):
    with SessionLocal() as db:
        guard(request,db,True)
        billing_lock(db,organization_id)
        row=db.get(CommercialInvoice,invoice_id)
        if not row or row.organization_id!=organization_id:
            raise HTTPException(404,'Recebível não encontrado.')
        reference=payload.payment_reference.strip()
        if len(reference)<3 or payload.amount_cents!=row.amount_cents or payload.paid_at>datetime.now(timezone.utc):
            raise HTTPException(422,'Valor, referência ou data de pagamento inválidos.')
        if row.status=='paid':
            from app.core.security import stamp
            if row.payment_reference==reference and stamp(row.paid_at)==payload.paid_at:
                return invoice_data(row)
            raise HTTPException(409,'Recebível já baixado.')
        if row.status!='open':
            raise HTTPException(409,'Recebível indisponível para baixa.')
        row.status='paid'
        row.payment_reference=reference
        row.paid_at=payload.paid_at.astimezone(timezone.utc)
        db.add(AuditLog(event='commercial_invoice_settled_manually',entity_type='commercial_invoice',
                        entity_id=row.id,details={'organization_id':organization_id,
                        'amount_cents':row.amount_cents,'payment_reference':reference,
                        'paid_at':row.paid_at.isoformat()}))
        try:
            db.flush()
            result=invoice_data(row)
            db.commit()
        except IntegrityError as exc:
            raise HTTPException(409,'Referência de pagamento já utilizada.') from exc
        return result


@router.post('/organizations/{organization_id}/invoices/{invoice_id}/void')
def void_invoice(request: Request,organization_id: int,invoice_id: int):
    with SessionLocal() as db:
        guard(request,db,True)
        billing_lock(db,organization_id)
        row=db.get(CommercialInvoice,invoice_id)
        if not row or row.organization_id!=organization_id:
            raise HTTPException(404,'Recebível não encontrado.')
        if row.status=='paid':
            raise HTTPException(409,'Recebível pago requer processo de estorno.')
        if row.status!='void':
            row.status='void'
            db.add(AuditLog(event='commercial_invoice_voided',entity_type='commercial_invoice',
                entity_id=row.id,details={'organization_id':organization_id}))
        result=invoice_data(row)
        db.commit()
        return result


# Sandbox-only administrative binding of an existing provider charge.
from decimal import Decimal, InvalidOperation
from sqlalchemy import text
from app.core.config import settings
from app.services.asaas_reconciliation import fetch_payment, PaymentUnavailable
from app.services.asaas_sandbox_bindings import verify_bound_invoice


class SandboxBindingIn(Input):
    customer_id: str = Field(pattern=r'^cus_[A-Za-z0-9_-]{1,100}$')
    payment_id: str = Field(pattern=r'^pay_[A-Za-z0-9_-]{1,100}$')


def sandbox_reference(organization_id, invoice_id):
    return f'leadcob-sandbox-org-{organization_id}-invoice-{invoice_id}'


def sandbox_match(data, payload, reference, amount_cents):
    try:
        amount = Decimal(str(data['value']))
        return (amount.is_finite() and amount * 100 == amount_cents
                and data['id'] == payload.payment_id
                and data['customer'] == payload.customer_id
                and data['externalReference'] == reference
                and data.get('deleted') is False
                and not data.get('refunds')
                and data.get('billingType') in {'PIX', 'BOLETO'}
                and data.get('status') in {'PENDING', 'OVERDUE', 'CONFIRMED', 'RECEIVED'})
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return False


@router.put('/organizations/{organization_id}/invoices/{invoice_id}/asaas-sandbox')
def bind_sandbox_payment(request: Request, organization_id: int, invoice_id: int,
                         payload: SandboxBindingIn):
    with SessionLocal() as db:
        guard(request, db, True)
        row = db.get(CommercialInvoice, invoice_id)
        if not row or row.organization_id != organization_id:
            raise HTTPException(404, 'Recebível não encontrado.')
        if row.status != 'open':
            raise HTTPException(409, 'Recebível não está aberto.')
        reference = sandbox_reference(organization_id, invoice_id)
        try:
            data = fetch_payment(payload.payment_id, settings.asaas_sandbox_api_key)
        except PaymentUnavailable as exc:
            raise HTTPException(503, 'Consulta sandbox indisponível.') from exc
        if not sandbox_match(data, payload, reference, row.amount_cents):
            raise HTTPException(422, 'Cobrança sandbox incompatível com o recebível.')
        # Serialize local mutations only after the network request returns.
        billing_lock(db, organization_id)
        db.refresh(row)
        if row.status != 'open' or row.organization_id != organization_id or not sandbox_match(data, payload, reference, row.amount_cents):
            raise HTTPException(409, 'Recebível alterado durante a consulta.')
        customer = db.execute(text('SELECT customer_id FROM asaas_sandbox_customers WHERE organization_id=:oid'),
                              {'oid': organization_id}).scalar_one_or_none()
        binding = db.execute(text('SELECT payment_id, external_reference FROM asaas_sandbox_payments WHERE invoice_id=:iid'),
                             {'iid': invoice_id}).mappings().one_or_none()
        if customer is not None and customer != payload.customer_id:
            raise HTTPException(409, 'Cliente sandbox já vinculado.')
        if binding is not None:
            if binding['payment_id'] != payload.payment_id or binding['external_reference'] != reference or customer != payload.customer_id:
                raise HTTPException(409, 'Vínculo sandbox já existente.')
            return {'environment': 'sandbox', 'bound': True, 'invoice_id': invoice_id}
        try:
            if customer is None:
                db.execute(text('INSERT INTO asaas_sandbox_customers (organization_id, customer_id) VALUES (:oid, :cid)'),
                           {'oid': organization_id, 'cid': payload.customer_id})
            db.execute(text('INSERT INTO asaas_sandbox_payments (invoice_id, payment_id, external_reference) VALUES (:iid, :pid, :ref)'),
                       {'iid': invoice_id, 'pid': payload.payment_id, 'ref': reference})
            db.add(AuditLog(event='asaas_sandbox_binding_created', entity_type='commercial_invoice',
                            entity_id=invoice_id, details={'organization_id': organization_id, 'environment': 'sandbox',
                            'payment_id': payload.payment_id, 'customer_id': payload.customer_id, 'external_reference': reference}))
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, 'Identificador sandbox já vinculado.') from exc
        return {'environment': 'sandbox', 'bound': True, 'invoice_id': invoice_id}


@router.get('/organizations/{organization_id}/invoices/{invoice_id}/asaas-sandbox')
def sandbox_payment_status(request: Request, organization_id: int, invoice_id: int):
    with SessionLocal() as db:
        guard(request, db)
        row = db.get(CommercialInvoice, invoice_id)
        if not row or row.organization_id != organization_id:
            raise HTTPException(404, 'Recebível não encontrado.')
        reference = sandbox_reference(organization_id, invoice_id)
        bound = db.execute(text('SELECT payment_id FROM asaas_sandbox_payments WHERE invoice_id=:iid'),
                           {'iid': invoice_id}).scalar_one_or_none() is not None
        try:
            verified = verify_bound_invoice(db, organization_id, invoice_id, settings.asaas_sandbox_api_key) if bound else False
        except PaymentUnavailable as exc:
            raise HTTPException(503, 'Consulta sandbox indisponível.') from exc
        return {'environment': 'sandbox', 'bound': bound, 'verified': verified,
                'external_reference': reference, 'invoice_id': invoice_id,
                'ledger_status': row.status}


from app.services.asaas_sandbox_issuance import issue_charge


class SandboxIssueIn(Input):
    billing_type: Literal['PIX', 'BOLETO']


@router.post('/organizations/{organization_id}/invoices/{invoice_id}/asaas-sandbox/issue', status_code=201)
def issue_sandbox_payment(request: Request, organization_id: int, invoice_id: int,
                          payload: SandboxIssueIn):
    with SessionLocal() as db:
        guard(request, db, True)
        if not settings.asaas_sandbox_api_key:
            raise HTTPException(503, 'Sandbox não configurado.')
        billing_lock(db, organization_id)
        row = db.get(CommercialInvoice, invoice_id)
        if not row or row.organization_id != organization_id:
            raise HTTPException(404, 'Recebível não encontrado.')
        if row.status != 'open' or date.fromisoformat(row.due_date) < date.today():
            raise HTTPException(409, 'Recebível indisponível para emissão.')
        customer = db.execute(text('SELECT customer_id FROM asaas_sandbox_customers WHERE organization_id=:oid'),
                              {'oid': organization_id}).scalar_one_or_none()
        if not customer:
            raise HTTPException(409, 'Cliente sandbox previamente vinculado obrigatório.')
        if db.execute(text('SELECT 1 FROM asaas_sandbox_payments WHERE invoice_id=:iid'),
                      {'iid': invoice_id}).first():
            raise HTTPException(409, 'Cobrança já vinculada.')
        reference = sandbox_reference(organization_id, invoice_id)
        args = dict(iid=invoice_id, cid=customer, ref=reference, kind=payload.billing_type,
                    amount=row.amount_cents, due=row.due_date, created=datetime.now(timezone.utc))
        try:
            db.execute(text("""INSERT INTO asaas_sandbox_issue_reservations
                (invoice_id, customer_id, external_reference, billing_type, amount_cents, due_date, created_at)
                VALUES (:iid, :cid, :ref, :kind, :amount, :due, :created)"""), args)
            db.add(AuditLog(event='asaas_sandbox_issue_reserved', entity_type='commercial_invoice',
                            entity_id=invoice_id, details={'organization_id': organization_id, 'reference': reference}))
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, 'Emissão já reservada; consulte o provedor antes de qualquer ação.') from exc
        # At most one POST per durable reservation. Never clear reservation on failure.
        try:
            payment_id = issue_charge(customer_id=customer, billing_type=payload.billing_type,
                amount_cents=args['amount'], due_date=args['due'], reference=reference,
                api_key=settings.asaas_sandbox_api_key)
        except (PaymentUnavailable, ValueError) as exc:
            raise HTTPException(503, 'Emissão incerta; consulte o sandbox pela referência. Não repita.') from exc
        billing_lock(db, organization_id)
        row = db.get(CommercialInvoice, invoice_id, populate_existing=True)
        if not row or row.organization_id != organization_id or row.status != 'open':
            raise HTTPException(409, 'Recebível alterado; cobrança sandbox requer revisão manual.')
        existing = db.execute(text('SELECT payment_id FROM asaas_sandbox_payments WHERE invoice_id=:iid'),
                              {'iid': invoice_id}).scalar_one_or_none()
        if existing and existing != payment_id:
            raise HTTPException(409, 'Conflito de vínculo; revisar manualmente.')
        try:
            if not existing:
                db.execute(text('INSERT INTO asaas_sandbox_payments (invoice_id,payment_id,external_reference) VALUES (:iid,:pid,:ref)'),
                           {'iid': invoice_id, 'pid': payment_id, 'ref': reference})
            db.add(AuditLog(event='asaas_sandbox_issued', entity_type='commercial_invoice',
                            entity_id=invoice_id, details={'organization_id': organization_id, 'payment_id': payment_id}))
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, 'Cobrança emitida; vínculo requer revisão manual.') from exc
        return {'environment': 'sandbox', 'invoice_id': invoice_id, 'payment_id': payment_id,
                'external_reference': reference, 'ledger_status': 'open'}
