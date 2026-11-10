"""Relatórios do período (issue #18)."""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services import reports

router = APIRouter(prefix="/api/reports", tags=["Relatórios"])


def _period(inicio, fim, dias):
    try:
        return reports.period(inicio, fim, dias)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/summary")
def summary(inicio: date | None = None, fim: date | None = None, dias: int | None = Query(default=None, ge=1, le=366),
            db: Session = Depends(get_db)):
    return reports.summary(db, *_period(inicio, fim, dias))


@router.get("/summary.csv")
def summary_csv(inicio: date | None = None, fim: date | None = None, dias: int | None = Query(default=None, ge=1, le=366),
                db: Session = Depends(get_db)):
    r = reports.summary(db, *_period(inicio, fim, dias))
    buf = io.StringIO()
    csv.writer(buf, delimiter=";").writerows(reports.to_csv_rows(r))
    name = f"leadcob-relatorio-{r['periodo']['inicio']}-a-{r['periodo']['fim']}.csv"
    return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f"attachment; filename={name}"})
