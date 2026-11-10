"""Exporta a base de empresas de um banco do LeadCob para JSON (só campos de pessoa jurídica).

Uso: python scripts/export_base.py base.db saida.json
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone

FIELDS = ["name", "trade_name", "cnpj", "segment", "city", "state", "cnae_main", "cnae_desc", "cnae_secondary",
          "registration_status", "company_size", "legal_nature", "capital_social", "opened_at", "target_profile",
          "registry_source", "registry_updated_at", "created_at"]


def main(src: str, out: str) -> int:
    con = sqlite3.connect(src); con.row_factory = sqlite3.Row
    cols = {r[1] for r in con.execute("PRAGMA table_info(companies)")}
    want = [f for f in FIELDS if f in cols]
    rows = [dict(r) for r in con.execute(f"SELECT {', '.join(want)} FROM companies WHERE cnpj IS NOT NULL ORDER BY capital_social DESC")]
    con.close()
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"gerado_em": datetime.now(timezone.utc).isoformat(), "empresas": rows}, f, ensure_ascii=False)
    print(f"{len(rows)} empresas exportadas para {out}")
    return len(rows)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
