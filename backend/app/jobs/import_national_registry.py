"""Controlled national registry intake; one UF and one source partition per invocation."""
import argparse
import json
import re
from collections import Counter
from datetime import date

from sqlalchemy import select, func
from app.db.models import Company, Suppression
from app.jobs import import_cnpj
from app.services.cnpj import clean_cnpj, is_valid_cnpj
from app.services.segments import profile_for

UFS = frozenset("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())


def prepare(records, uf):
    """Validate an entire slice before any writes; keep only corporate fields."""
    rows = []
    seen = set()
    for rec in records:
        key = clean_cnpj(rec.get("cnpj"))
        name = str(rec.get("razao_social") or "").strip()
        nature = str(rec.get("natureza_codigo") or "")
        profile = profile_for(rec.get("cnae_principal"))
        if (not is_valid_cnpj(key) or key in seen or rec.get("uf") != uf
                or rec.get("situacao_cadastral") != "ATIVA" or not profile
                or not re.fullmatch(r"[0-9]{4}", nature) or nature == "2135"
                or rec.get("individual") or not name or re.search(r"[0-9]{11}\s*$", name)):
            raise ValueError("Lote incompatível com política cadastral; nenhuma gravação iniciada.")
        seen.add(key)
        rows.append(dict(rec, cnpj=key, target_profile=profile))
    return rows


def insert_missing(db, rows, release, batch_size=500):
    """Insert-only. Preserve every pre-existing CRM record; reruns are idempotent
    under a single writer. Caller must serialize imports and other CNPJ creation."""
    if not 1 <= batch_size <= 1000:
        raise ValueError("Lote de gravação inválido.")
    result = Counter(created=0, existing=0, suppressed=0)
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        keys = [r["cnpj"] for r in batch]
        # Stored CNPJs are canonical 14-character identifiers; uppercase covers legacy lowercase.
        present = set(db.scalars(select(func.upper(Company.cnpj)).where(
            func.upper(Company.cnpj).in_(keys))))
        blocked = {clean_cnpj(v) for v in db.scalars(select(Suppression.cnpj).where(
            func.upper(Suppression.cnpj).in_(keys)))}
        blocked.update(clean_cnpj(v) for v in db.scalars(
            select(Company.cnpj).join(Suppression, Suppression.company_id == Company.id)
            .where(func.upper(Company.cnpj).in_(keys))))
        try:
            for rec in batch:
                key = rec["cnpj"]
                if key in blocked:
                    result["suppressed"] += 1
                elif key in present:
                    result["existing"] += 1
                else:
                    company = Company(cnpj=key, name=rec["razao_social"][:220])
                    import_cnpj.apply_registry(company, rec, source=f"Receita Federal — dados abertos {release}")
                    db.add(company)
                    result["created"] += 1
            db.commit()
        except Exception:
            db.rollback()
            raise
    return dict(result)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uf", required=True, choices=sorted(UFS))
    parser.add_argument("--part", required=True, type=int, choices=range(10))
    parser.add_argument("--release", required=True, help="Competência fixa AAAA-MM")
    parser.add_argument("--local-dir")
    parser.add_argument("--max-records", type=int, default=150000)
    parser.add_argument("--apply", action="store_true", help="Grava novas empresas; exige backup e escritor único")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", args.release):
        parser.error("Competência inválida.")
    if date.fromisoformat(args.release + "-01") > date.today():
        parser.error("Competência futura.")
    if not 1 <= args.max_records <= 300000:
        parser.error("Limite permitido: 1 a 300.000.")
    opts = ["--uf", args.uf, "--parts", str(args.part), "--release", args.release,
            "--include-branches", "--max-records", str(args.max_records),
            "--dry-run", "--summary-only", "--strict-layout"]
    if args.local_dir:
        opts += ["--local-dir", args.local_dir]
    if args.apply:
        from app.db.database import check_schema_revision
        check_schema_revision()
    rows = prepare(import_cnpj.main(opts), args.uf)
    report = {"uf": args.uf, "part": args.part, "release": args.release,
              "eligible": len(rows), "mode": "apply" if args.apply else "preview",
              "coverage_complete": False, "profiles": dict(Counter(r["target_profile"] for r in rows))}
    if args.apply:
        from app.db.database import SessionLocal
        with SessionLocal() as db:
            report.update(insert_missing(db, rows, args.release))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)
    return report


if __name__ == "__main__":
    main()
