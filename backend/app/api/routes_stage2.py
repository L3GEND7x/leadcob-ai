"""v0.5.2 — Etapa 2: gerador de abordagens, inteligência de cobrança, laboratório de negociação e scripts."""
from __future__ import annotations

import json
import hashlib
from uuid import UUID
from decimal import Decimal
from sqlalchemy.exc import IntegrityError
from fastapi.encoders import jsonable_encoder
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from app.api.routes_crm import company_sheet
from app.db.database import get_db
from app.db.models import Company, Portfolio, PortfolioItem, PortfolioEvent
from app.services import approach, collection, negotiation
from app.services.crm import MANAUS, audit, blocked_reason, get_settings

router = APIRouter(prefix="/api")
SCRIPTS_FILE = Path(__file__).resolve().parents[3] / "config" / "scripts.json"


# ------------------------------------------------------------- gerador de abordagens
@router.get("/companies/{company_id}/approach")
def company_approach(company_id: int, db: Session = Depends(get_db)):
    sheet = company_sheet(company_id, db)
    c = db.get(Company, company_id)
    if reason := blocked_reason(db, c):
        raise HTTPException(409, f"{reason} Nenhuma abordagem é gerada para empresas que não devem ser contatadas.")
    if sheet["band"] == "concorrente":
        raise HTTPException(409, "Empresa do ramo de cobrança (concorrente): não é cliente potencial.")
    return {"company_id": company_id, "company_name": sheet["name"], **approach.build(sheet, get_settings(db))}


# ------------------------------------------------------------- biblioteca de scripts
@router.get("/scripts")
def scripts(categoria: str | None = None, q: str | None = None):
    data = json.loads(SCRIPTS_FILE.read_text(encoding="utf-8"))
    items = data["scripts"]
    if categoria:
        items = [s for s in items if s["categoria"] == categoria]
    if q:
        ql = q.lower()
        items = [s for s in items if ql in (s["titulo"] + " " + s["texto"] + " " + s["quando_usar"]).lower()]
    return {"nota": data["nota"], "categorias": sorted({s["categoria"] for s in data["scripts"]}), "scripts": items}


# ------------------------------------------------------------- laboratório de negociação
class Simulation(BaseModel):
    valor_original: float = Field(gt=0)
    vencimento: date
    data_base: date
    multa_pct: float = Field(default=0, ge=0, le=100)
    juros_mes_pct: float = Field(default=0, ge=0, le=100)
    juros_tipo: str = Field(default="simples", pattern="^(simples|composto)$")
    correcao_pct: float = Field(default=0, ge=-100, le=1000)
    desconto_pct: float = Field(default=0, ge=0, le=100)
    desconto_sobre: str = Field(default="encargos", pattern="^(encargos|total)$")
    primeiro_vencimento: date | None = None
    entrada: float = Field(default=0, ge=0)
    parcelas: int = Field(default=1, ge=1, le=120)
    juros_parcelamento_mes_pct: float = Field(default=0, ge=0, le=100)


@router.post("/negotiation/simulate")
def simulate(p: Simulation):
    data = p.model_dump()
    data["vencimento"], data["data_base"] = p.vencimento.isoformat(), p.data_base.isoformat()
    try:
        if p.primeiro_vencimento:
            data["primeiro_vencimento"] = p.primeiro_vencimento.isoformat()
        return negotiation.simulate(data)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# ------------------------------------------------------------- inteligência de cobrança (carteiras)
class PortfolioIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    csv: str = Field(min_length=10, max_length=20_000_000)
    client_company_id: int | None = None
    reference_date: date | None = None
    source_note: str = Field(default="", max_length=500)
    number_format: str = Field(default="auto", pattern="^(auto|br|us)$")
    accept_partial: bool = False
    accept_duplicates: bool = False


def _ref_today() -> date:
    return datetime.now(MANAUS).date()


def _portfolio_view(pf: Portfolio, reference: date | None = None) -> dict:
    ref = reference or date.fromisoformat(pf.reference_date)
    items = [{"amount": i.amount, "due_date": i.due_date, "paid_date": i.paid_date, "debtor_type": i.debtor_type, "events": [{"kind": e.kind, "reversed_kind": next((prior.kind for prior in i.events if prior.id == e.reversal_of), None), "amount": e.amount, "effective_date": e.effective_date} for e in i.events]} for i in pf.items]
    return {"id": pf.id, "name": pf.name, "archived": pf.archived_at is not None, "importacao": pf.import_report, "client_company_id": pf.client_company_id, "source_note": pf.source_note,
            "created_at": pf.created_at.isoformat() if pf.created_at else None, "titulos": len(items),
            **collection.analyze(items, ref), "items": [{"id": i.id, "ref": i.ref, "amount": i.amount, "due_date": i.due_date,
                "paid_date": i.paid_date, "events": [{"id": e.id, "kind": e.kind,
                "amount": e.amount, "effective_date": e.effective_date, "reference": e.reference,
                "reversal_of": e.reversal_of} for e in i.events]}
                for i in pf.items[:500]]}


@router.post("/portfolios", status_code=201)
def import_portfolio(payload: PortfolioIn, db: Session = Depends(get_db)):
    if payload.client_company_id and not db.get(Company, payload.client_company_id):
        raise HTTPException(404, "Empresa cliente não encontrada.")
    try:
        parsed = collection.parse_csv(payload.csv, payload.number_format)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not parsed["items"]:
        raise HTTPException(400, {"mensagem": "Nenhum título válido no arquivo.", "erros": parsed["errors"][:20]})
    if parsed["error_count"] and not payload.accept_partial:
        raise HTTPException(409, {"mensagem": "Há linhas inválidas. Revise a prévia antes de importar parcialmente.",
                                  "total_erros": parsed["error_count"], "amostra": parsed["errors"]})
    if parsed["possible_duplicates"] and not payload.accept_duplicates:
        raise HTTPException(409, {"mensagem": "Revise possíveis duplicidades antes de confirmar.", "linhas": parsed["possible_duplicates"]})
    ref = payload.reference_date or _ref_today()
    key = hashlib.sha256(json.dumps({"client": payload.client_company_id, "name": payload.name, "ref": ref.isoformat(), "items": parsed["items"]}, sort_keys=True).encode()).hexdigest()
    existing = db.query(Portfolio).filter_by(import_key=key).first()
    if existing:
        return {**_portfolio_view(existing), "reused": True}
    report = {"titulos_importados": len(parsed["items"]), "linhas_com_erro": parsed["errors"], "total_erros": parsed["error_count"], "possiveis_duplicidades": parsed["possible_duplicates"], "colunas_ignoradas": parsed["ignored_columns"], "colunas_pessoais_descartadas": parsed["personal_columns_dropped"]}
    pf = Portfolio(name=payload.name, client_company_id=payload.client_company_id, reference_date=ref.isoformat(),
                   source_note=payload.source_note, import_key=key, import_report=report)
    pf.items = [PortfolioItem(**it) for it in parsed["items"]]
    db.add(pf)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.query(Portfolio).filter_by(import_key=key).first()
        if existing:
            return {**_portfolio_view(existing), "reused": True}
        raise
    audit(db, "portfolio_imported", "portfolio", pf.id, {"titulos": len(parsed["items"]), "erros": len(parsed["errors"]),
                                                          "colunas_pessoais_descartadas": parsed["personal_columns_dropped"]})
    db.commit(); db.refresh(pf)
    return _portfolio_view(pf)


@router.get("/portfolios")
def list_portfolios(archived: bool = False, db: Session = Depends(get_db)):
    rows = db.query(Portfolio).filter(Portfolio.archived_at.isnot(None) if archived else Portfolio.archived_at.is_(None)).options(selectinload(Portfolio.items)).order_by(Portfolio.created_at.desc()).all()
    return [{k: v for k, v in _portfolio_view(pf).items() if k not in {"faixas", "items", "importacao"}} for pf in rows]


@router.get("/portfolios/{pid}")
def get_portfolio(pid: int, reference_date: date | None = Query(default=None), db: Session = Depends(get_db)):
    pf = db.query(Portfolio).options(selectinload(Portfolio.items)).filter_by(id=pid).first()
    if not pf:
        raise HTTPException(404, "Carteira não encontrada.")
    return _portfolio_view(pf, reference_date)


@router.delete("/portfolios/{pid}")
def delete_portfolio(pid: int, db: Session = Depends(get_db)):
    pf = db.get(Portfolio, pid)
    if not pf:
        raise HTTPException(404, "Carteira não encontrada.")
    audit(db, "portfolio_deleted", "portfolio", pid, {"name": pf.name})
    pf.archived_at = datetime.now(MANAUS)
    db.commit()
    return {"ok": True}


@router.post("/portfolios/preview")
def preview_portfolio(payload: PortfolioIn):
    try:
        parsed = collection.parse_csv(payload.csv, payload.number_format)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {**parsed, "items": parsed["items"][:20], "valid_count": len(parsed["items"]),
            "total": str(sum((negotiation.money(it["amount"]) for it in parsed["items"]), Decimal(0)))}


@router.post("/portfolios/{pid}/restore")
def restore_portfolio(pid: int, db: Session = Depends(get_db)):
    pf = db.get(Portfolio, pid)
    if not pf:
        raise HTTPException(404, "Carteira não encontrada.")
    pf.archived_at = None
    audit(db, "portfolio_restored", "portfolio", pid, {})
    db.commit()
    return {"ok": True}


class PortfolioMovementIn(BaseModel):
    kind: str = Field(pattern="^(payment|discount)$")
    amount: float = Field(gt=0)
    effective_date: date
    reference: str = Field(min_length=2, max_length=120)
    request_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$")


@router.post("/portfolios/{pid}/items/{item_id}/movements", status_code=201)
def add_movement(pid: int, item_id: int, payload: PortfolioMovementIn, db: Session = Depends(get_db)):
    if len(payload.request_id) != 36:
        raise HTTPException(422, "Identificador de operação inválido.")
    try:
        UUID(payload.request_id)
    except ValueError as exc:
        raise HTTPException(422, "Identificador de operação inválido.") from exc
    previous = db.query(PortfolioEvent).filter_by(request_id=payload.request_id).first()
    if previous:
        if previous.item_id != item_id:
            raise HTTPException(409, "Identificador usado em outra operação.")
        return {"id": previous.id, "reused": True}
    item = db.query(PortfolioItem).filter_by(id=item_id, portfolio_id=pid).with_for_update().first()
    if not item or item.portfolio.archived_at:
        raise HTTPException(404, "Título indisponível.")
    if item.paid_date and not item.events:
        raise HTTPException(409, "Título legado com baixa integral. Revise antes de lançar movimentações.")
    amount = negotiation.money(payload.amount)
    if amount <= 0:
        raise HTTPException(400, "Valor deve ser positivo em centavos.")
    balance = negotiation.money(item.amount) - sum((e.amount * (-1 if e.kind == 'reversal' else 1)
                                                    for e in item.events), Decimal(0))
    if amount > balance:
        raise HTTPException(409, "Movimentação maior que o saldo remanescente.")
    event = PortfolioEvent(item_id=item.id, kind=payload.kind, amount=amount,
                           effective_date=payload.effective_date.isoformat(), reference=payload.reference,
                           request_id=payload.request_id)
    db.add(event)
    try:
        db.flush()
        audit(db, 'portfolio_movement_added', 'portfolio_event', event.id,
              {'portfolio_id': pid, 'item_id': item_id, 'kind': event.kind, 'amount': str(amount)})
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = db.query(PortfolioEvent).filter_by(request_id=payload.request_id).first()
        if previous and previous.item_id == item_id:
            return {"id": previous.id, "reused": True}
        raise
    return {"id": event.id, "balance": float(balance - amount)}


class ReversalIn(BaseModel):
    effective_date: date
    reference: str = Field(min_length=2, max_length=120)
    request_id: str


@router.post("/portfolios/{pid}/movements/{movement_id}/reverse", status_code=201)
def reverse_movement(pid: int, movement_id: int, payload: ReversalIn, db: Session = Depends(get_db)):
    previous = db.query(PortfolioEvent).filter_by(request_id=payload.request_id).first()
    if previous:
        if previous.reversal_of != movement_id:
            raise HTTPException(409, "Identificador usado em outra operação.")
        return {"id": previous.id, "reused": True}
    event = db.query(PortfolioEvent).filter_by(id=movement_id).with_for_update().first()
    if not event or event.item.portfolio_id != pid or event.item.portfolio.archived_at or event.kind == 'reversal':
        raise HTTPException(404, "Movimentação indisponível.")
    if db.query(PortfolioEvent).filter_by(reversal_of=movement_id).first():
        raise HTTPException(409, "Movimentação já estornada.")
    if payload.effective_date.isoformat() < event.effective_date:
        raise HTTPException(400, "Estorno deve ocorrer após a movimentação original.")
    reversal = PortfolioEvent(item_id=event.item_id, kind='reversal', amount=event.amount,
                              effective_date=payload.effective_date.isoformat(), reference=payload.reference,
                              reversal_of=event.id, request_id=payload.request_id)
    db.add(reversal)
    try:
        db.flush()
        audit(db, 'portfolio_movement_reversed', 'portfolio_event', reversal.id,
              {'original_id': event.id, 'portfolio_id': pid, 'amount': str(event.amount)})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Estorno já registrado.")
    return {"id": reversal.id}
