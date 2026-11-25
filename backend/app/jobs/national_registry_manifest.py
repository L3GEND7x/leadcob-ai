"""Durable local manifest for nationwide registry slices; preview only by default.

Use a private persistent volume, never the public repository. One manifest
belongs to one release, one execution mode and one source configuration.
"""
import argparse
import json
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.jobs import import_national_registry as intake

ORDER = "AM PA RR RO AC AP TO MA PI CE RN PB PE AL SE BA MT MS GO DF MG ES RJ SP PR SC RS".split()
assert set(ORDER) == intake.UFS and len(ORDER) == 27


def now():
    return datetime.now(timezone.utc).isoformat()


def connect(path):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=30000")
    return db


def init(db, release, mode, local_dir, max_records):
    config = dict(release=release, mode=mode, local_dir=local_dir, max_records=max_records)
    with db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)")
        db.execute("""CREATE TABLE IF NOT EXISTS cells (
            uf TEXT NOT NULL, part INTEGER NOT NULL, ordinal INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
            token TEXT, started_at TEXT, finished_at TEXT, report TEXT, failure TEXT,
            PRIMARY KEY (uf, part))""")
        row = db.execute("SELECT value FROM config WHERE id=1").fetchone()
        if row is not None and json.loads(row[0]) != config:
            raise ValueError("Manifesto pertence a outra competência, modo ou configuração.")
        if row is None:
            db.execute("INSERT INTO config VALUES (1, ?)", (json.dumps(config, sort_keys=True),))
            db.executemany("INSERT INTO cells(uf,part,ordinal) VALUES(?,?,?)",
                           [(uf, part, i*10+part) for i, uf in enumerate(ORDER) for part in range(10)])


def claim(db, uf=None, retry_failed=False, max_attempts=3):
    with db:
        db.execute("BEGIN IMMEDIATE")
        # Serialize a manifest even across different command invocations.
        if db.execute("SELECT 1 FROM cells WHERE state='running' LIMIT 1").fetchone():
            return None
        states = ("pending", "failed") if retry_failed else ("pending",)
        query = "SELECT uf,part FROM cells WHERE state IN (%s) AND attempts<?" % ",".join("?" for _ in states)
        params = [*states, max_attempts]
        if uf:
            query += " AND uf=?"
            params.append(uf)
        row = db.execute(query+" ORDER BY ordinal LIMIT 1", params).fetchone()
        if row is None:
            return None
        token = uuid4().hex
        db.execute("""UPDATE cells SET state='running', attempts=attempts+1, token=?,
                      started_at=?, finished_at=NULL, report=NULL, failure=NULL
                      WHERE uf=? AND part=?""", (token, now(), row["uf"], row["part"]))
        return row["uf"], row["part"], token


def finish(db, cell, report=None, failure=None):
    uf, part, token = cell
    if (report is None) == (failure is None):
        raise ValueError("Informe resultado ou falha.")
    with db:
        db.execute("BEGIN IMMEDIATE")
        cur = db.execute("""UPDATE cells SET state=?,finished_at=?,report=?,failure=?,token=NULL
            WHERE uf=? AND part=? AND token=? AND state='running'""",
            ("succeeded" if report is not None else "failed", now(),
             json.dumps(report, sort_keys=True) if report is not None else None, failure, uf, part, token))
        if cur.rowcount != 1:
            raise RuntimeError("Reserva não corresponde à execução ativa.")


def recover(db, uf, part):
    # Operator must verify the previous process is stopped. Never auto-expire a live writer.
    with db:
        db.execute("BEGIN IMMEDIATE")
        cur = db.execute("""UPDATE cells SET state='failed',finished_at=?,failure='interrupted',
                    token=NULL WHERE uf=? AND part=? AND state='running'""", (now(), uf, part))
        return cur.rowcount == 1


def validate_report(report, release, mode, uf, part):
    if not isinstance(report, dict) or any(report.get(k) != v for k,v in
            dict(release=release,mode=mode,uf=uf,part=part,municipality_code=None).items()):
        raise ValueError("Relatório não corresponde à célula.")
    if report.get("coverage_complete") is not False:
        raise ValueError("Relatório deve manter limite de cobertura.")
    n = report.get("eligible")
    if type(n) is not int or n < 0:
        raise ValueError("Contador inválido.")
    keys = ["created", "existing", "suppressed"]
    if mode == "apply":
        if any(type(report.get(k)) is not int or report[k] < 0 for k in keys) or sum(report[k] for k in keys) != n:
            raise ValueError("Contadores de aplicação não conciliam.")
    # Persist only aggregate fields, never arbitrary source strings or rows.
    result = dict(eligible=n)
    if mode == "apply":
        result.update({k:report[k] for k in keys})
    return result


def summary(db):
    counts = dict.fromkeys(("pending","running","failed","succeeded"), 0)
    totals = dict.fromkeys(("eligible","created","existing","suppressed"), 0)
    states = {uf:dict.fromkeys(counts,0) for uf in ORDER}
    for row in db.execute("SELECT uf,state,report FROM cells"):
        counts[row["state"]] += 1
        states[row["uf"]][row["state"]] += 1
        if row["state"] == "succeeded":
            for k,v in json.loads(row["report"]).items():
                totals[k] += v
    return {"cells_total":270, "counts":counts, "by_uf":states, "totals":totals,
            "all_cells_succeeded":counts["succeeded"] == 270,
            "coverage_complete":False,
            "note":"Totais de execuções bem-sucedidas; não censo, não contagem única nacional, nem histórico de inserções após falhas parciais."}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True, help="Arquivo SQLite em volume privado persistente")
    p.add_argument("--release", required=True)
    p.add_argument("--local-dir")
    p.add_argument("--uf", choices=ORDER)
    p.add_argument("--max-records", type=int, default=150000)
    p.add_argument("--max-jobs", type=int, default=1)
    p.add_argument("--retry-failed", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--confirm-single-writer", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--recover-part", type=int, choices=range(10))
    p.add_argument("--confirm-process-stopped", action="store_true")
    a = p.parse_args(argv)
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", a.release) or a.release[:4]=="0000":
        p.error("Competência inválida.")
    if date.fromisoformat(a.release+"-01") > date.today():
        p.error("Competência futura.")
    if not 1 <= a.max_jobs <= 10 or not 1 <= a.max_records <= 300000:
        p.error("Limites inválidos (1–10 células; até 300 mil candidatos).")
    if a.apply and not a.confirm_single_writer and not a.status and a.recover_part is None:
        p.error("Aplicação exige confirmação de backup e janela de escritor único.")
    if a.recover_part is not None and (not a.uf or not a.confirm_process_stopped or a.status):
        p.error("Recuperação exige UF e confirmação de que a execução anterior terminou.")
    mode = "apply" if a.apply else "preview"
    local_dir = str(Path(a.local_dir).resolve()) if a.local_dir else None
    with closing(connect(a.manifest)) as db:
        init(db,a.release,mode,local_dir,a.max_records)
        if a.recover_part is not None:
            if not recover(db,a.uf,a.recover_part):
                p.error("Célula não está em execução.")
        elif not a.status:
            for _ in range(a.max_jobs):
                cell = claim(db,a.uf,a.retry_failed)
                if cell is None:
                    break
                uf,part,_token = cell
                opts = ["--uf",uf,"--part",str(part),"--release",a.release,
                        "--max-records",str(a.max_records)]
                if local_dir:
                    opts += ["--local-dir",local_dir]
                if a.apply:
                    opts += ["--apply"]
                try:
                    report = validate_report(intake.main(opts),a.release,mode,uf,part)
                except (Exception, SystemExit):
                    finish(db,cell,failure="intake_failed")
                    # Stop immediately: do not spend resources on subsequent slices after a failure.
                    print(json.dumps(summary(db),ensure_ascii=False),flush=True)
                    raise SystemExit(1) from None
                finish(db,cell,report=report)
        result=summary(db)
        print(json.dumps(result,ensure_ascii=False),flush=True)
        return result


if __name__=="__main__":
    main()
