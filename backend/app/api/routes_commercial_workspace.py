"""Commercial workspace HTTP boundary; never use the legacy session or tables."""
from contextlib import contextmanager
from app.core.config import settings
from app.services.commercial_entitlements import enforce, lock_organization, usage
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.exc import IntegrityError

from app.api.routes_commercial_auth import COOKIE, _enabled, _origin
from app.core.account_access import AccessDenied, authorize
from app.db.database import SessionLocal
from app.services import workspace_leads as leads, workspace_tasks as tasks, workspace_portfolios as portfolios

router = APIRouter(prefix='/api/commercial/workspace/{organization_id}', tags=['Commercial workspace'])


@contextmanager
def operation(request, organization_id, write=False, resource=None, subscription_exempt=False):
    _enabled()
    if write:
        _origin(request)
    token = request.cookies.get(COOKIE, '')
    csrf = request.headers.get('x-csrf-token', '')
    with SessionLocal() as db:
        try:
            authorize(db, token, organization_id, 'write' if write else 'read', csrf=csrf)
            if write:
                lock_organization(db, organization_id)
                principal = authorize(db, token, organization_id, 'write', csrf=csrf)
                if settings.commercial_entitlements_enabled and not subscription_exempt:
                    enforce(db, organization_id, resource, locked=True)
            if write:
                from app.core.security import actor
                audit_token = actor.set(f'commercial:{principal.organization_id}:{principal.user_id}')
                try:
                    yield db, token, csrf
                    db.commit()
                finally:
                    actor.reset(audit_token)
            else:
                yield db, token, csrf
        except AccessDenied as exc:
            raise HTTPException(403, 'Acesso não autorizado.') from exc
        except (leads.LeadNotFound, tasks.TaskNotFound, portfolios.PortfolioNotFound) as exc:
            raise HTTPException(404, 'Registro não encontrado.') from exc
        except ValueError as exc:
            raise HTTPException(422, 'Dados inválidos ou referência duplicada.') from exc
        except IntegrityError as exc:
            raise HTTPException(409, 'Conflito de registro.') from exc


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class LeadIn(Input):
    name: str = Field(min_length=1, max_length=220)
    notes: str = Field(default='', max_length=8000)
    stage: Literal['identified', 'contacted', 'negotiation', 'won', 'lost'] = 'identified'


class TaskIn(Input):
    title: str = Field(min_length=1, max_length=250)
    due_date: str = Field(min_length=10, max_length=10)


class Completion(Input):
    completed: bool


class PortfolioIn(Input):
    name: str = Field(min_length=1, max_length=160)
    reference_date: str = Field(min_length=10, max_length=10)


class TitleIn(Input):
    reference: str = Field(min_length=1, max_length=80)
    amount: str = Field(min_length=1, max_length=32, pattern=r'^\d{1,14}(\.\d{1,2})?$')
    due_date: str = Field(min_length=10, max_length=10)


def _lead(x):
    return dict(id=x.id, name=x.name, notes=x.notes, stage=x.stage)


def _task(x):
    return dict(id=x.id, title=x.title, due_date=x.due_date, completed_at=x.completed_at)


def _portfolio(x):
    return dict(id=x.id, name=x.name, reference_date=x.reference_date)


def _title(x):
    return dict(id=x.id, reference=x.reference, amount=format(x.amount, '.2f'),
                due_date=x.due_date, paid_date=x.paid_date)


@router.get('/leads')
def list_leads(request: Request, organization_id: int, limit: int = Query(100, ge=1, le=250),
               offset: int = Query(0, ge=0)):
    with operation(request, organization_id) as (db, token, _):
        return [_lead(x) for x in leads.list_leads(db, token, organization_id, limit=limit, offset=offset)]


@router.post('/leads', status_code=201)
def create_lead(request: Request, organization_id: int, payload: LeadIn):
    with operation(request, organization_id, True, resource='leads') as (db, token, csrf):
        return _lead(leads.create_lead(db, token, organization_id, csrf, **payload.model_dump()))


@router.get('/leads/{lead_id}')
def get_lead(request: Request, organization_id: int, lead_id: int):
    with operation(request, organization_id) as (db, token, _):
        return _lead(leads.get_lead(db, token, organization_id, lead_id))


@router.put('/leads/{lead_id}')
def update_lead(request: Request, organization_id: int, lead_id: int, payload: LeadIn):
    with operation(request, organization_id, True) as (db, token, csrf):
        return _lead(leads.update_lead(db, token, organization_id, csrf, lead_id, **payload.model_dump()))


@router.delete('/leads/{lead_id}')
def delete_lead(request: Request, organization_id: int, lead_id: int):
    with operation(request, organization_id, True) as (db, token, csrf):
        leads.delete_lead(db, token, organization_id, csrf, lead_id)
        return {'ok': True}


@router.get('/tasks')
def list_tasks(request: Request, organization_id: int, completed: bool | None = None,
               limit: int = Query(100, ge=1, le=250), offset: int = Query(0, ge=0)):
    with operation(request, organization_id) as (db, token, _):
        return [_task(x) for x in tasks.list_tasks(db, token, organization_id, completed=completed, limit=limit, offset=offset)]


@router.post('/tasks', status_code=201)
def create_task(request: Request, organization_id: int, payload: TaskIn):
    with operation(request, organization_id, True, resource='tasks') as (db, token, csrf):
        return _task(tasks.create_task(db, token, organization_id, csrf, **payload.model_dump()))


@router.patch('/tasks/{task_id}')
def complete_task(request: Request, organization_id: int, task_id: int, payload: Completion):
    with operation(request, organization_id, True) as (db, token, csrf):
        return _task(tasks.set_completed(db, token, organization_id, csrf, task_id, completed=payload.completed))


@router.delete('/tasks/{task_id}')
def delete_task(request: Request, organization_id: int, task_id: int):
    with operation(request, organization_id, True) as (db, token, csrf):
        tasks.delete_task(db, token, organization_id, csrf, task_id)
        return {'ok': True}


@router.get('/portfolios')
def list_portfolios(request: Request, organization_id: int, limit: int = Query(100, ge=1, le=250),
                    offset: int = Query(0, ge=0)):
    with operation(request, organization_id) as (db, token, _):
        return [_portfolio(x) for x in portfolios.list_portfolios(db, token, organization_id, limit=limit, offset=offset)]


@router.post('/portfolios', status_code=201)
def create_portfolio(request: Request, organization_id: int, payload: PortfolioIn):
    with operation(request, organization_id, True, resource='portfolios') as (db, token, csrf):
        return _portfolio(portfolios.create_portfolio(db, token, organization_id, csrf, **payload.model_dump()))


@router.get('/portfolios/{portfolio_id}/titles')
def list_titles(request: Request, organization_id: int, portfolio_id: int,
                limit: int = Query(100, ge=1, le=250), offset: int = Query(0, ge=0)):
    with operation(request, organization_id) as (db, token, _):
        return [_title(x) for x in portfolios.list_titles(db, token, organization_id, portfolio_id, limit=limit, offset=offset)]


@router.post('/portfolios/{portfolio_id}/titles', status_code=201)
def add_title(request: Request, organization_id: int, portfolio_id: int, payload: TitleIn):
    with operation(request, organization_id, True, resource='titles') as (db, token, csrf):
        return _title(portfolios.add_title(db, token, organization_id, csrf, portfolio_id, **payload.model_dump()))


@router.get('/portfolios/{portfolio_id}/summary')
def portfolio_summary(request: Request, organization_id: int, portfolio_id: int, as_of: str = Query(min_length=10, max_length=10)):
    with operation(request, organization_id) as (db, token, _):
        summary = portfolios.summarize_portfolio(db, token, organization_id, portfolio_id, as_of=as_of)
        return {k: format(v, '.2f') if isinstance(v, Decimal) else v for k, v in summary.items()}


from app.services import workspace_contacts as contacts, workspace_settings as preferences


class ContactIn(Input):
    cnpj: str = Field(min_length=14, max_length=18)
    kind: Literal['email', 'website', 'phone', 'whatsapp', 'linkedin', 'instagram', 'facebook']
    value: str = Field(min_length=3, max_length=500)
    source_url: str = Field(min_length=8, max_length=1000)
    institutional: bool


class SuppressionIn(Input):
    cnpj: str = Field(min_length=14, max_length=18)
    reason: str = Field(min_length=1, max_length=250)


class PreferencesIn(Input):
    timezone_name: str = Field(min_length=1, max_length=80)
    followup_days: list[int] = Field(min_length=1, max_length=10)
    default_page_size: int = Field(ge=10, le=250)


def _contact(x):
    return dict(id=x.id, cnpj=x.cnpj, kind=x.kind, value=x.value,
                source_url=x.source_url, status='a_verificar')


@router.get('/contacts')
def list_contacts(request: Request, organization_id: int, cnpj: str | None = Query(None, max_length=18),
                  limit: int = Query(100, ge=1, le=250), offset: int = Query(0, ge=0)):
    with operation(request, organization_id) as (db, token, _):
        return [_contact(x) for x in contacts.list_contacts(db, token, organization_id,
                cnpj=cnpj, limit=limit, offset=offset)]


@router.post('/contacts', status_code=201)
def add_contact(request: Request, organization_id: int, payload: ContactIn):
    with operation(request, organization_id, True, resource='contacts') as (db, token, csrf):
        return _contact(contacts.add_contact(db, token, organization_id, csrf, **payload.model_dump()))


@router.post('/suppressions', status_code=201)
def suppress_company(request: Request, organization_id: int, payload: SuppressionIn):
    with operation(request, organization_id, True, subscription_exempt=True) as (db, token, csrf):
        row = contacts.suppress_company(db, token, organization_id, csrf, **payload.model_dump())
        return dict(cnpj=row.cnpj, reason=row.reason)


@router.get('/settings')
def get_preferences(request: Request, organization_id: int):
    with operation(request, organization_id) as (db, token, _):
        return preferences.get_settings(db, token, organization_id)


@router.put('/settings')
def update_preferences(request: Request, organization_id: int, payload: PreferencesIn):
    with operation(request, organization_id, True) as (db, token, csrf):
        return preferences.update_settings(db, token, organization_id, csrf, **payload.model_dump())


@router.get('/subscription')
def get_workspace_subscription(request: Request, organization_id: int):
    from app.services.commercial_subscriptions import describe
    with operation(request,organization_id) as (db,token,_):
        return {**describe(db,organization_id), 'usage':usage(db,organization_id),
                'enforcement_enabled':settings.commercial_entitlements_enabled}


@router.get('/assistant/context')
def assistant_context(request: Request, organization_id: int):
    from app.services.workspace_assistant import context
    with operation(request, organization_id) as (db, token, _):
        return context(db, token, organization_id)


@router.get('/prospects/{cnpj}')
def lookup_prospect(request: Request, organization_id: int, cnpj: str):
    from app.services.workspace_prospects import lookup
    if len(cnpj)>18:
        raise HTTPException(422,"CNPJ inválido.")
    with operation(request, organization_id) as (db, token, _):
        return lookup(db, token, organization_id, cnpj)


class AssistantMessageIn(Input):
    request_id: str = Field(pattern=r'^[0-9a-fA-F-]{36}$', min_length=36, max_length=36)
    prompt: str = Field(min_length=1,max_length=2000)


@router.get('/assistant/history')
def assistant_history(request: Request, organization_id: int):
    from app.services.workspace_assistant import history
    with operation(request,organization_id) as (db,token,_):
        return history(db,token,organization_id)


@router.post('/assistant/generate')
def assistant_generate(request: Request, organization_id: int, payload: AssistantMessageIn):
    from app.services.workspace_assistant import generate
    if not payload.prompt.strip():
        raise HTTPException(422,'Informe uma pergunta.')
    with operation(request,organization_id,True) as (db,token,csrf):
        return generate(db,token,organization_id,csrf,payload.request_id,payload.prompt.strip())


@router.get('/registry-search/options')
def registry_search_options(request: Request, organization_id: int):
    from app.services.workspace_registry_search import options
    with operation(request,organization_id) as (db,token,_):
        return options(db,token,organization_id)


class RegistrySearchIn(Input):
    uf: str = Field(pattern=r'^[A-Za-z]{2}$')
    city: str = Field(min_length=1,max_length=100)
    segment: str | None = Field(default=None,max_length=80)
    channel: str | None = Field(default=None,max_length=20)
    limit: int = Field(default=30,ge=1,le=50)
    offset: int = Field(default=0,ge=0,le=5000)


class RegistryImportIn(Input):
    cnpj: str = Field(min_length=14,max_length=18)


@router.post('/registry-search')
def registry_search(request: Request, organization_id: int, payload: RegistrySearchIn):
    from app.services.workspace_registry_search import search, consume_quota
    with operation(request,organization_id,True) as (db,token,csrf):
        consume_quota(db,token,organization_id,csrf)
        # Persist the quota before the potentially expensive scan. Errors must not
        # make repeated requests free; the organization lock serialized increments.
        db.commit()
        return search(db,token,organization_id,**payload.model_dump())


@router.post('/registry-import', status_code=201)
def registry_import(request: Request, organization_id: int, payload: RegistryImportIn):
    from app.services.workspace_registry_search import import_prospect
    with operation(request,organization_id,True,resource='leads') as (db,token,csrf):
        return import_prospect(db,token,organization_id,csrf,payload.cnpj)
