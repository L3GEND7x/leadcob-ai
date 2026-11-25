"""Bounded transfer from completed private staging to the application database.

Preview by default. Apply requires a restored backup and exclusive writer window.
A retry starts the slice again; already committed canonical CNPJs are skipped.
"""
import argparse
from collections import Counter
from contextlib import closing, nullcontext
import json
import os
from pathlib import Path
import re
import sqlite3

from app.collectors import rfb_files as R
from app.jobs import import_national_registry as intake, national_registry_stage as stage
from app.jobs.import_cnpj import Source, lookup_table
from app.services.cnpj import is_valid_cnpj


def open_readonly(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file() or (os.name == "posix" and path.stat().st_mode & 0o077):
        raise ValueError("Staging deve ser um arquivo privado (0600).")
    db = sqlite3.connect(path.as_uri()+"?mode=ro", uri=True, timeout=30)
    db.execute("PRAGMA query_only=ON")
    return db


def config_for(db, release):
    row = db.execute("SELECT value FROM config WHERE id=1").fetchone()
    if not row:
        raise ValueError("Staging sem configuração.")
    config = json.loads(row[0])
    if config.get("release") != release or config.get("version") != 1:
        raise ValueError("Competência ou versão de staging divergente.")
    if not stage.status(db)["staging_complete"]:
        raise ValueError("Staging incompleto.")
    return config


def load_lookups(config):
    local_dir = config.get("source_dir")
    with (nullcontext(None) if local_dir else R.client()) as http:
        src = Source(config["release"], http, local_dir)
        return tuple(lookup_table(src, filename)
                     for filename in ("Municipios.zip", "Cnaes.zip", "Naturezas.zip"))


def validate_scope(db, uf, part, lookups):
    if uf not in intake.UFS or type(part) is not int or not 0 <= part <= 9:
        raise ValueError("Escopo inválido.")
    report = stage.reconciliation(db,uf,part)
    if report["unresolved"]:
        raise ValueError("Identidades sem conciliação; transferência bloqueada.")
    municipalities, cnaes, natures = lookups
    # Validate lookup completeness before application writes. Do not silently
    # import companies with no city or ambiguous registry metadata.
    for col, table in (("s.municipality",municipalities),("s.cnae",cnaes),("e.nature",natures)):
        rows = db.execute(f"""SELECT DISTINCT {col}
            FROM establishments s JOIN entities e ON e.root=s.root
            WHERE s.uf=? AND s.part=? AND e.corporate=1""",(uf,part))
        if any(not str(table.get(value) or "").strip() for (value,) in rows):
            raise ValueError("Tabela de referência incompleta para o escopo.")
    return report


def batches(db, uf, part, lookups, batch_size=500):
    if not 1<=batch_size<=500:
        raise ValueError("Lote deve ter de 1 a 500 registros.")
    municipalities,cnaes,natures=lookups
    after=""
    while True:
        rows=db.execute("""SELECT s.cnpj,s.root,s.uf,s.municipality,s.cnae,
            s.secondary,s.opened_at,s.profile,e.name,e.nature,e.size,e.capital
            FROM establishments s JOIN entities e ON e.root=s.root
            WHERE s.uf=? AND s.part=? AND s.cnpj>? AND e.corporate=1
            ORDER BY s.cnpj LIMIT ?""",(uf,part,after,batch_size)).fetchall()
        if not rows:
            return
        records=[]
        for cnpj,root,state,municipality,cnae,secondary,opened,profile,name,nature,size,capital in rows:
            if not is_valid_cnpj(cnpj) or cnpj[:8]!=root or not re.fullmatch(r"[0-9]{7}",cnae):
                raise ValueError("Identificador cadastral inconsistente no staging.")
            records.append(dict(cnpj=cnpj,uf=state,municipio=municipalities[municipality],
                municipio_codigo=municipality,cnae_principal=cnae,cnae_descricao=cnaes[cnae],
                cnaes_secundarios=(secondary or "").split(",") if secondary else [],
                data_inicio_atividade=opened,target_profile=profile,razao_social=name,
                natureza_codigo=nature,natureza_juridica=natures[nature],porte=size,
                capital_social=capital,situacao_cadastral="ATIVA"))
        yield intake.prepare(records,uf)
        after=rows[-1][0]


def transfer(db, uf, part, lookups, release, target=None, batch_size=500):
    report=validate_scope(db,uf,part,lookups)
    totals=Counter(created=0,existing=0,suppressed=0)
    count=0
    # Preview and apply both validate the actual rows; preview never opens target.
    for batch in batches(db,uf,part,lookups,batch_size):
        count+=len(batch)
        if target is not None:
            totals.update(intake.insert_missing(target,batch,release,batch_size=batch_size))
    if count!=report["eligible"] or (target is not None and sum(totals.values())!=count):
        raise RuntimeError("Contagem de transferência não conciliada.")
    report.update(release=release,mode="apply" if target is not None else "preview",
                  validated=count)
    if target is not None:
        report.update(totals)
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage",required=True)
    p.add_argument("--release",required=True)
    p.add_argument("--uf",required=True,choices=sorted(intake.UFS))
    p.add_argument("--part",required=True,type=int,choices=range(10))
    p.add_argument("--batch-size",type=int,default=500)
    p.add_argument("--apply",action="store_true")
    p.add_argument("--confirm-backup-and-exclusive-writer",action="store_true")
    a=p.parse_args(argv)
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])",a.release) or a.release[:4]=="0000":
        p.error("Competência inválida.")
    if not 1<=a.batch_size<=500:
        p.error("Lote deve ter de 1 a 500 registros.")
    if a.apply and not a.confirm_backup_and_exclusive_writer:
        p.error("Aplicação exige backup restaurado e janela de escritor único.")
    with closing(open_readonly(a.stage)) as db:
        db.execute("BEGIN")  # consistent read snapshot throughout transfer
        config=config_for(db,a.release)
        lookups=load_lookups(config)
        if a.apply:
            from app.db.database import check_schema_revision, SessionLocal
            check_schema_revision()
            with SessionLocal() as target:
                if target.get_bind().dialect.name!="postgresql":
                    raise ValueError("Aplicação exige PostgreSQL.")
                result=transfer(db,a.uf,a.part,lookups,a.release,target,a.batch_size)
        else:
            result=transfer(db,a.uf,a.part,lookups,a.release,batch_size=a.batch_size)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True),flush=True)
    return result


if __name__=="__main__":
    main()
