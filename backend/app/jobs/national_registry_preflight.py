"""Read-only national partition sizing. No company data or database writes."""
import argparse
from collections import Counter, defaultdict
from contextlib import nullcontext
from datetime import date
import json
import re

from app.collectors import rfb_files as R
from app.jobs.import_cnpj import Source, filter_establishments
from app.jobs.import_national_registry import UFS


def assess(rows, max_records=150000):
    """One streaming scan; counts are pre-join candidates, not eligible CNPJs."""
    if not 1 <= max_records <= 300000:
        raise ValueError("Limite inválido.")
    stats = {}
    by_uf = Counter()
    municipalities = defaultdict(Counter)
    unknown = 0
    for row in filter_establishments(rows, None, None, only_headquarters=False, stats=stats):
        uf = row["uf"]
        if uf not in UFS:
            unknown += 1
            continue
        by_uf[uf] += 1
        code = row["municipio_codigo"]
        # Keep only official-shaped municipal codes; no arbitrary source values.
        municipalities[uf][code if re.fullmatch(r"[0-9]{4}", code or "") else "unknown"] += 1
    result = {}
    for uf in sorted(UFS):
        n = by_uf[uf]
        result[uf] = {
            "candidates_before_company_join": n,
            "exceeds_limit": n > max_records,
            "municipality_candidates": dict(sorted(municipalities[uf].items())),
            "municipalities_exceeding_limit": sorted(k for k,v in municipalities[uf].items() if v > max_records),
        }
    return {"records_read": stats.get("read",0), "invalid_cnpjs": stats.get("invalid_cnpj",0),
            "bad_layout":stats.get("bad_layout",0), "unrecognized_uf_candidates":unknown,
            "candidate_rows":sum(by_uf.values()), "by_uf":result,
            "max_records":max_records, "coverage_complete":False,
            "note":"Estimativa de linhas candidatas antes de deduplicação, natureza jurídica, supressão e junção Empresas; não é número de empresas elegíveis."}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--release", required=True)
    p.add_argument("--part", type=int, choices=range(10), required=True)
    p.add_argument("--local-dir")
    p.add_argument("--max-records", type=int, default=150000)
    a = p.parse_args(argv)
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])",a.release) or a.release[:4]=="0000":
        p.error("Competência inválida.")
    if date.fromisoformat(a.release+"-01") > date.today():
        p.error("Competência futura.")
    if not 1 <= a.max_records <= 300000:
        p.error("Limite inválido.")
    with (nullcontext(None) if a.local_dir else R.client()) as http:
        src = Source(a.release,http,a.local_dir)
        result = assess(src.rows(f"Estabelecimentos{a.part}.zip"), a.max_records)
    result.update(release=a.release,part=a.part)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True),flush=True)
    if result["bad_layout"] or result["invalid_cnpjs"] or result["unrecognized_uf_candidates"]:
        raise SystemExit(1)
    return result


if __name__=="__main__":
    main()
