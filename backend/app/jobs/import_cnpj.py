"""Importa a base de empresas-alvo a partir dos dados abertos do CNPJ.

Uso (a partir de backend/):
    python -m app.jobs.import_cnpj --segments atacado,credito_fomento --uf AM,PA --parts 0-9
    python -m app.jobs.import_cnpj --segments educacao_privada --uf SC --parts 1 --limit 200 --dry-run

Custo medido em 09/11/2026: ~12.500 linhas/s (~0,85 MB/s comprimidos). Cada
arquivo Estabelecimentos tem ~340 MB (o 0 tem ~2,3 GB); a publicação inteira
leva ~1h45. Filtrar por UF NÃO reduz a leitura (os arquivos não são ordenados
por UF), só o volume gravado. Rode como job mensal, fora do horário de uso.

O resultado é CADASTRO (quem se parece com o perfil), não sinal de demanda.
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from datetime import datetime, timezone

from app.collectors import rfb_files as R
from app.services.cnpj import PORTE, SITUACAO
from app.services.segments import SEGMENTS, profile_for

# Layout validado com dados reais (publicação 2026-10): 30 colunas.
E_BASICO, E_ORDEM, E_DV, E_MATRIZ, E_FANTASIA, E_SITUACAO = 0, 1, 2, 3, 4, 5
E_INICIO, E_CNAE, E_CNAE_SEC, E_UF, E_MUNICIPIO = 10, 11, 12, 19, 20
# Empresas: 7 colunas.
P_BASICO, P_RAZAO, P_NATUREZA, P_QUALIF, P_CAPITAL, P_PORTE = 0, 1, 2, 3, 4, 5


def parse_parts(spec: str) -> list[int]:
    out = []
    for chunk in spec.split(","):
        if "-" in chunk:
            a, b = chunk.split("-"); out.extend(range(int(a), int(b) + 1))
        elif chunk.strip():
            out.append(int(chunk))
    return sorted(set(out))


def lookup_table(release: str, name: str, http) -> dict[str, str]:
    return {row[0]: row[1] for row in R.iter_remote_rows(release, name, http) if len(row) >= 2}


def filter_establishments(rows, segments: list[str] | None, ufs: set[str] | None, only_active: bool = True,
                          only_headquarters: bool = True, limit: int | None = None, stats: dict | None = None):
    """Filtra linhas de Estabelecimentos. Função pura: testável sem rede."""
    stats = stats if stats is not None else {}
    for row in rows:
        stats["read"] = stats.get("read", 0) + 1
        if len(row) != 30:
            stats["bad_layout"] = stats.get("bad_layout", 0) + 1
            continue
        if only_active and row[E_SITUACAO] != "02":
            continue
        if only_headquarters and row[E_MATRIZ] != "1":
            continue
        if ufs and row[E_UF] not in ufs:
            continue
        profile = profile_for(row[E_CNAE], segments)
        if not profile:
            continue
        stats["matched"] = stats.get("matched", 0) + 1
        yield {
            "cnpj": row[E_BASICO] + row[E_ORDEM] + row[E_DV],
            "cnpj_basico": row[E_BASICO],
            "nome_fantasia": row[E_FANTASIA].strip() or None,
            "situacao_cadastral": SITUACAO.get(row[E_SITUACAO], row[E_SITUACAO]),
            "data_inicio_atividade": f"{row[E_INICIO][:4]}-{row[E_INICIO][4:6]}-{row[E_INICIO][6:]}" if len(row[E_INICIO]) == 8 else None,
            "cnae_principal": row[E_CNAE],
            "cnaes_secundarios": [c for c in row[E_CNAE_SEC].split(",") if c],
            "uf": row[E_UF],
            "municipio_codigo": row[E_MUNICIPIO],
            "matriz": row[E_MATRIZ] == "1",
            "target_profile": profile,
            # E-mail, telefones, endereço e sócios: descartados de propósito (LGPD).
        }
        if limit and stats["matched"] >= limit:
            return


def fill_companies(rows, wanted: dict[str, dict], stats: dict | None = None, stop_after: str | None = None):
    """Completa razão social/porte/natureza/capital a partir de Empresas (função pura).

    Os arquivos Empresas vêm ordenados por CNPJ básico (verificado em 2026-10).
    Com `stop_after`, a leitura para ao passar desse CNPJ — mas só enquanto a
    ordenação se confirmar linha a linha; se quebrar, lê até o fim.
    """
    stats = stats if stats is not None else {}
    previous, ordered = "", True
    for row in rows:
        if len(row) != 7:
            continue
        basico = row[P_BASICO]
        if basico < previous:
            ordered = False
            stats["order_broken"] = True
        previous = basico
        if stop_after and ordered and basico > stop_after:
            stats["early_stop"] = stats.get("early_stop", 0) + 1
            return
        rec = wanted.get(basico)
        if rec is None:
            continue
        rec["razao_social"] = row[P_RAZAO].strip() or None
        rec["natureza_codigo"] = row[P_NATUREZA]
        rec["porte"] = PORTE.get(row[P_PORTE], row[P_PORTE] or None)
        try:
            rec["capital_social"] = float(row[P_CAPITAL].replace(".", "").replace(",", "."))
        except ValueError:
            rec["capital_social"] = None
        stats["filled"] = stats.get("filled", 0) + 1


def fill_with_fallback(open_rows, by_basico: dict[str, dict], basicos: list[str], stats: dict):
    """Leitura com parada antecipada; se faltar algum CNPJ do arquivo, relê inteiro.

    A parada antecipada depende de o arquivo estar ordenado. Se não estiver (ou se
    a Receita mudar o formato), a releitura garante que nada se perde em silêncio.
    """
    fill_companies(open_rows(), by_basico, stats, stop_after=max(basicos))
    missing = [b for b in basicos if "razao_social" not in by_basico[b]]
    if missing and stats.get("early_stop"):
        stats["full_rereads"] = stats.get("full_rereads", 0) + 1
        fill_companies(open_rows(), {b: by_basico[b] for b in missing}, stats)
        missing = [b for b in basicos if "razao_social" not in by_basico[b]]
    stats["not_found"] = stats.get("not_found", 0) + len(missing)


def plan_company_parts(starts: dict[int, str], basicos) -> dict[int, list[str]]:
    """Distribui CNPJs básicos pelos arquivos Empresas conforme o 1º CNPJ de cada um."""
    bounds = sorted((first, part) for part, first in starts.items())
    plan: dict[int, list[str]] = {}
    for b in sorted(basicos):
        part = None
        for first, p in bounds:
            if b >= first:
                part = p
            else:
                break
        if part is not None:
            plan.setdefault(part, []).append(b)
    return plan


def company_part_starts(release: str, http) -> dict[int, str]:
    starts = {}
    for part in range(10):
        f = R.HttpRangeFile(R.file_url(release, f"Empresas{part}.zip"), http, block=256 * 1024)
        first = next(R.iter_csv_rows(io.BufferedReader(f)), None)
        if first:
            starts[part] = first[P_BASICO]
    return starts


def save(records: list[dict], release: str) -> tuple[int, int]:
    from app.db.database import SessionLocal, ensure_schema
    from app.db.models import Company
    ensure_schema()
    db = SessionLocal(); created = updated = 0
    try:
        for rec in records:
            c = db.query(Company).filter_by(cnpj=rec["cnpj"]).first()
            if c:
                updated += 1
            else:
                c = Company(cnpj=rec["cnpj"], name=rec.get("razao_social") or rec.get("nome_fantasia") or f"CNPJ {rec['cnpj']}")
                db.add(c); created += 1
            apply_registry(c, rec, source=f"Receita Federal — dados abertos {release}")
        db.commit()
    finally:
        db.close()
    return created, updated


def apply_registry(c, rec: dict, source: str):
    """Aplica campos cadastrais a uma Company (usado pelo job e pela consulta individual)."""
    if rec.get("razao_social"):
        c.name = rec["razao_social"][:220]
    for attr, key in [("trade_name", "nome_fantasia"), ("cnae_main", "cnae_principal"), ("cnae_desc", "cnae_descricao"),
                      ("registration_status", "situacao_cadastral"), ("company_size", "porte"),
                      ("legal_nature", "natureza_juridica"), ("capital_social", "capital_social"),
                      ("opened_at", "data_inicio_atividade"), ("state", "uf"), ("target_profile", "target_profile")]:
        if rec.get(key) not in (None, ""):
            setattr(c, attr, rec[key])
    if rec.get("municipio"):
        c.city = rec["municipio"][:100]
    if rec.get("cnaes_secundarios") is not None:
        c.cnae_secondary = ",".join(rec["cnaes_secundarios"])[:2000]
    if not c.segment and rec.get("cnae_descricao"):
        c.segment = rec["cnae_descricao"][:120]
    c.registry_source = source
    c.registry_updated_at = datetime.now(timezone.utc)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release", help="AAAA-MM (padrão: a mais recente)")
    ap.add_argument("--segments", default="", help="perfis separados por vírgula: " + ", ".join(SEGMENTS))
    ap.add_argument("--uf", default="", help="UFs separadas por vírgula (vazio = Brasil)")
    ap.add_argument("--parts", default="0-9", help="arquivos Estabelecimentos/Empresas (ex.: 0-9, 1, 2,5)")
    ap.add_argument("--include-branches", action="store_true", help="incluir filiais (padrão: só matrizes)")
    ap.add_argument("--skip-companies", action="store_true", help="não ler Empresas (sem razão social/porte)")
    ap.add_argument("--min-size", choices=["01", "03", "05"], help="porte mínimo: 01 ME, 03 EPP, 05 demais")
    ap.add_argument("--limit", type=int, help="máximo de empresas (para testes)")
    ap.add_argument("--dry-run", action="store_true", help="não grava no banco")
    a = ap.parse_args(argv)

    segments = [s for s in a.segments.split(",") if s] or None
    unknown = [s for s in segments or [] if s not in SEGMENTS]
    if unknown:
        ap.error(f"perfis desconhecidos: {unknown}")
    ufs = {u.strip().upper() for u in a.uf.split(",") if u.strip()} or None
    t0 = time.time(); stats: dict = {}
    with R.client() as http:
        release = a.release or R.latest_release(http)
        print(f"Publicação {release} · perfis {segments or 'todos'} · UF {sorted(ufs) if ufs else 'todas'}", flush=True)
        cnaes = lookup_table(release, "Cnaes.zip", http)
        municipios = lookup_table(release, "Municipios.zip", http)
        naturezas = lookup_table(release, "Naturezas.zip", http)
        found: dict[str, dict] = {}
        for part in parse_parts(a.parts):
            remaining = (a.limit - len(found)) if a.limit else None
            if remaining is not None and remaining <= 0:
                break
            rows = R.iter_remote_rows(release, f"Estabelecimentos{part}.zip", http, block=8 * 1024 * 1024)
            for rec in filter_establishments(rows, segments, ufs, only_headquarters=not a.include_branches,
                                             limit=remaining, stats=stats):
                rec["cnae_descricao"] = cnaes.get(rec["cnae_principal"])
                rec["municipio"] = municipios.get(rec["municipio_codigo"])
                found[rec["cnpj"]] = rec
            print(f"  Estabelecimentos{part}: {stats.get('read', 0)} linhas lidas, {len(found)} empresas no perfil "
                  f"({time.time() - t0:.0f}s)", flush=True)
        if found and not a.skip_companies:
            by_basico = {r["cnpj_basico"]: r for r in found.values()}
            # Empresas é particionado por faixa de CNPJ básico: lê só os arquivos
            # necessários e para ao passar do maior CNPJ procurado em cada um.
            plan = plan_company_parts(company_part_starts(release, http), by_basico)
            for part, basicos in sorted(plan.items()):
                fill_with_fallback(lambda: R.iter_remote_rows(release, f"Empresas{part}.zip", http, block=8 * 1024 * 1024),
                                   by_basico, basicos, stats)
                print(f"  Empresas{part}: {stats.get('filled', 0)}/{len(by_basico)} completadas ({time.time() - t0:.0f}s)", flush=True)
            if stats.get("full_rereads"):
                print(f"  AVISO: {stats['full_rereads']} arquivo(s) Empresas relidos por completo (ordem inesperada).", flush=True)
            if stats.get("not_found"):
                print(f"  {stats['not_found']} CNPJ(s) sem registro em Empresas.", flush=True)
            for r in found.values():
                if r.get("natureza_codigo"):
                    r["natureza_juridica"] = naturezas.get(r["natureza_codigo"], r["natureza_codigo"])
    records = list(found.values())
    if a.min_size:
        order = {"MICRO EMPRESA": 1, "EMPRESA DE PEQUENO PORTE": 3, "DEMAIS": 5}
        records = [r for r in records if order.get(r.get("porte"), 0) >= int(a.min_size)]
    print(f"Total: {len(records)} empresas · linhas fora do layout: {stats.get('bad_layout', 0)}", flush=True)
    if a.dry_run:
        for r in records[:10]:
            print("  ", r["cnpj"], r.get("razao_social") or r.get("nome_fantasia"), r["cnae_principal"], r.get("municipio"), r["uf"], r.get("porte"))
        return records
    created, updated = save(records, release)
    print(f"Gravado: {created} novas, {updated} atualizadas", flush=True)
    return records


if __name__ == "__main__":
    sys.exit(0 if main() is not None else 1)
