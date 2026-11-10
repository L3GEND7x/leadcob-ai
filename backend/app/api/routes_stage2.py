"""v0.5.2 — Etapa 2: gerador de abordagens, inteligência de cobrança, laboratório de negociação e scripts."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from app.api.routes_crm import company_sheet
from app.db.database import get_db
from app.db.models import Company, Portfolio, PortfolioItem
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
    entrada: float = Field(default=0, ge=0)
    parcelas: int = Field(default=1, ge=1, le=120)
    juros_parcelamento_mes_pct: float = Field(default=0, ge=0, le=100)


@router.post("/negotiation/simulate")
def simulate(p: Simulation):
    data = p.model_dump()
    data["vencimento"], data["data_base"] = p.vencimento.isoformat(), p.data_base.isoformat()
    try:
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


def _ref_today() -> date:
    return datetime.now(MANAUS).date()


def _portfolio_view(pf: Portfolio, reference: date | None = None) -> dict:
    ref = reference or date.fromisoformat(pf.reference_date)
    items = [{"amount": i.amount, "due_date": i.due_date, "paid_date": i.paid_date, "debtor_type": i.debtor_type} for i in pf.items]
    return {"id": pf.id, "name": pf.name, "client_company_id": pf.client_company_id, "source_note": pf.source_note,
            "created_at": pf.created_at.isoformat() if pf.created_at else None, "titulos": len(items),
            **collection.analyze(items, ref)}


@router.post("/portfolios", status_code=201)
def import_portfolio(payload: PortfolioIn, db: Session = Depends(get_db)):
    if payload.client_company_id and not db.get(Company, payload.client_company_id):
        raise HTTPException(404, "Empresa cliente não encontrada.")
    try:
        parsed = collection.parse_csv(payload.csv)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not parsed["items"]:
        raise HTTPException(400, {"mensagem": "Nenhum título válido no arquivo.", "erros": parsed["errors"][:20]})
    ref = payload.reference_date or _ref_today()
    pf = Portfolio(name=payload.name, client_company_id=payload.client_company_id, reference_date=ref.isoformat(),
                   source_note=payload.source_note)
    pf.items = [PortfolioItem(**it) for it in parsed["items"]]
    db.add(pf); db.flush()
    audit(db, "portfolio_imported", "portfolio", pf.id, {"titulos": len(parsed["items"]), "erros": len(parsed["errors"]),
                                                          "colunas_pessoais_descartadas": parsed["personal_columns_dropped"]})
    db.commit(); db.refresh(pf)
    return {**_portfolio_view(pf), "importacao": {"titulos_importados": len(parsed["items"]), "linhas_com_erro": parsed["errors"][:20],
                                                   "colunas_ignoradas": parsed["ignored_columns"],
                                                   "colunas_pessoais_descartadas": parsed["personal_columns_dropped"]}}


@router.get("/portfolios")
def list_portfolios(db: Session = Depends(get_db)):
    rows = db.query(Portfolio).options(selectinload(Portfolio.items)).order_by(Portfolio.created_at.desc()).all()
    return [{k: v for k, v in _portfolio_view(pf).items() if k != "faixas"} for pf in rows]


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
    db.delete(pf); db.commit()
    return {"ok": True}
