"""Private disk-backed national staging; scan each source ZIP once per release.

No application database access. Use a private local persistent volume.
A completed source file is immutable within this stage.
"""
import argparse
from collections import Counter
from contextlib import closing, nullcontext
from datetime import date
import json
import os
from pathlib import Path
import re
import sqlite3

from app.collectors import rfb_files as R
from app.jobs.import_cnpj import Source, filter_establishments
from app.jobs.import_national_registry import UFS
from app.services.cnpj import PORTE

FILES = tuple(f"{kind}{i}.zip" for kind in ("Empresas", "Estabelecimentos") for i in range(10))


def connect(path):
    path = Path(path)
    if not path.exists():
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    if os.name == "posix" and path.stat().st_mode & 0o077:
        raise ValueError("Arquivo de staging deve ser privado (permissões 0600).")
    db = sqlite3.connect(path, timeout=30)
    db.execute("PRAGMA busy_timeout=30000")
    return db


def init(db, release, source_dir):
    config = json.dumps({"release":release,"source_dir":source_dir,"version":1},sort_keys=True)
    with db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)")
        old = db.execute("SELECT value FROM config WHERE id=1").fetchone()
        if old and old[0]!=config:
            raise ValueError("Staging vinculado a outra competência ou fonte.")
        db.execute("INSERT OR IGNORE INTO config VALUES(1,?)",(config,))
        db.execute("CREATE TABLE IF NOT EXISTS files (name TEXT PRIMARY KEY, counters TEXT NOT NULL)")
        db.execute("""CREATE TABLE IF NOT EXISTS entities (
            root TEXT PRIMARY KEY, corporate INTEGER NOT NULL, name TEXT,
            nature TEXT, size TEXT, capital REAL) WITHOUT ROWID""")
        db.execute("""CREATE TABLE IF NOT EXISTS establishments (
            cnpj TEXT PRIMARY KEY, root TEXT NOT NULL, uf TEXT NOT NULL,
            municipality TEXT NOT NULL, cnae TEXT NOT NULL, secondary TEXT,
            opened_at TEXT, profile TEXT NOT NULL, part INTEGER NOT NULL) WITHOUT ROWID""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_stage_scope ON establishments(uf,part,cnpj)")


def chunks(rows, size=2000):
    batch=[]
    for row in rows:
        batch.append(row)
        if len(batch)==size:
            yield batch
            batch=[]
    if batch:
        yield batch


def entity_rows(rows, stats):
    for row in rows:
        stats["read"]+=1
        if len(row)!=7 or not re.fullmatch(r"[0-9A-Z]{8}",row[0]) or not re.fullmatch(r"[0-9]{4}",row[2]):
            raise ValueError("Layout Empresas incompatível.")
        root,name,nature=row[0],row[1].strip(),row[2]
        corporate=nature!="2135" and bool(name) and not re.search(r"[0-9]{11}\s*$",name)
        if not corporate:
            # Retain a join marker only; never persist individual names or capital.
            stats["excluded_identity"]+=1
            yield (root,0,None,None,None,None)
            continue
        try:
            capital=float(row[4].replace(".","").replace(",","."))
            if not 0<=capital<1e15:
                capital=None
        except ValueError:
            capital=None
        stats["corporate"]+=1
        yield (root,1,name[:220],nature,PORTE.get(row[5]),capital)


def establishment_rows(rows,part,stats):
    scan={}
    for rec in filter_establishments(rows,None,None,only_headquarters=False,stats=scan):
        if rec["uf"] not in UFS:
            stats["outside_ufs"]+=1
            continue
        if not re.fullmatch(r"[0-9]{4}",rec["municipio_codigo"]):
            raise ValueError("Município sem código válido.")
        stats["candidates"]+=1
        yield (rec["cnpj"],rec["cnpj_basico"],rec["uf"],rec["municipio_codigo"],
               rec["cnae_principal"],",".join(rec["cnaes_secundarios"])[:2000],
               rec["data_inicio_atividade"],rec["target_profile"],part)
    stats.update(scan)
    if scan.get("bad_layout") or scan.get("invalid_cnpj"):
        raise ValueError("Estabelecimentos com layout ou CNPJ inválido.")


def stage_file(db,src,name):
    if name not in FILES:
        raise ValueError("Arquivo não permitido.")
    stats=Counter()
    with db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM files WHERE name=?",(name,)).fetchone():
            return {"file":name,"already_staged":True}
        if name.startswith("Empresas"):
            rows=entity_rows(src.rows(name),stats)
            sql="INSERT INTO entities VALUES(?,?,?,?,?,?)"
        else:
            part=int(name.removeprefix("Estabelecimentos").removesuffix(".zip"))
            rows=establishment_rows(src.rows(name),part,stats)
            sql="INSERT INTO establishments VALUES(?,?,?,?,?,?,?,?,?)"
        for batch in chunks(rows):
            db.executemany(sql,batch)
        db.execute("INSERT INTO files VALUES(?,?)",(name,json.dumps(stats,sort_keys=True)))
    return {"file":name,"already_staged":False,"counts":dict(stats)}


def status(db):
    completed={r[0] for r in db.execute("SELECT name FROM files")}
    # Avoid scanning millions of rows on every status request.
    return {"completed_files":sorted(completed),"remaining_files":[f for f in FILES if f not in completed],
            "files_total":len(FILES),"staging_complete":completed==set(FILES),"coverage_complete":False}


def reconciliation(db,uf,part):
    if not status(db)["staging_complete"]:
        raise ValueError("Conciliação exige os 20 arquivos completos.")
    counts=db.execute("""SELECT count(*),
        count(CASE WHEN e.root IS NULL THEN 1 END),
        count(CASE WHEN e.corporate=0 THEN 1 END),
        count(CASE WHEN e.corporate=1 THEN 1 END)
        FROM establishments s LEFT JOIN entities e ON e.root=s.root
        WHERE s.uf=? AND s.part=?""",(uf,part)).fetchone()
    total,unresolved,excluded,eligible=counts
    return dict(uf=uf,part=part,candidates=total,unresolved=unresolved,
                excluded_identity=excluded,eligible=eligible,coverage_complete=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage",required=True)
    p.add_argument("--release",required=True)
    p.add_argument("--local-dir")
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument("--file",choices=FILES)
    group.add_argument("--status",action="store_true")
    group.add_argument("--reconcile",action="store_true")
    p.add_argument("--uf",choices=sorted(UFS))
    p.add_argument("--part",type=int,choices=range(10))
    a=p.parse_args(argv)
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])",a.release) or a.release[:4]=="0000":
        p.error("Competência inválida.")
    if date.fromisoformat(a.release+"-01")>date.today():
        p.error("Competência futura.")
    if a.reconcile and (not a.uf or a.part is None):
        p.error("Conciliação exige UF e partição.")
    local_dir=str(Path(a.local_dir).resolve()) if a.local_dir else None
    with closing(connect(a.stage)) as db:
        init(db,a.release,local_dir)
        if a.file:
            with (nullcontext(None) if local_dir else R.client()) as http:
                result=stage_file(db,Source(a.release,http,local_dir),a.file)
        elif a.reconcile:
            result=reconciliation(db,a.uf,a.part)
        else:
            result=status(db)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True),flush=True)
    if result.get("unresolved",0):
        raise SystemExit(1)
    return result


if __name__=="__main__":
    main()
