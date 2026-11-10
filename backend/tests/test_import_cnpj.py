"""Importador de dados abertos do CNPJ com arquivos sintéticos no layout real (30 e 7 colunas)."""
import csv
import io
import re
import zipfile

import httpx
import pytest

from app.collectors import rfb_files as R
from app.jobs import import_cnpj as J


def est(basico, cnae, uf="AM", situacao="02", matriz="1", fantasia="", ordem="0001", dv="00", mun="0255"):
    row = [""] * 30
    row[0], row[1], row[2], row[3], row[4], row[5] = basico, ordem, dv, matriz, fantasia, situacao
    row[10], row[11], row[12], row[19], row[20] = "20100115", cnae, "4639701,4637199", uf, mun
    row[21], row[22], row[27] = "92", "33334444", "pessoa@exemplo.com"  # devem ser descartados
    return row


def emp(basico, razao, porte="03", capital="150000,00", natureza="2062"):
    return [basico, razao, natureza, "49", capital, porte, ""]


def zipped(rows, name="F.CSV"):
    text = io.StringIO()
    csv.writer(text, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\n").writerows(rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, text.getvalue().encode("latin-1"))
    return buf.getvalue()


def test_filter_establishments():
    rows = [est("11111111", "6491300", fantasia="FOMENTO A"),          # ok
            est("22222222", "6491300", situacao="08"),                  # baixada
            est("33333333", "6491300", matriz="2"),                     # filial
            est("44444444", "6491300", uf="SP"),                        # outra UF
            est("55555555", "4711302"),                                 # varejo: fora do perfil
            est("66666666", "8513900", fantasia="ESCOLA Ç"),            # ok (educação)
            ["curta"]]
    stats = {}
    out = list(J.filter_establishments(rows, ["credito_fomento", "educacao_privada"], {"AM"}, stats=stats))
    assert [r["cnpj_basico"] for r in out] == ["11111111", "66666666"]
    assert out[0]["target_profile"] == "credito_fomento" and out[0]["cnpj"] == "11111111000100"
    assert stats["bad_layout"] == 1
    assert "pessoa@exemplo.com" not in str(out) and "33334444" not in str(out)


def test_fill_companies_stops_early_when_ordered():
    wanted = {"20000000": {}, "30000000": {}}
    stats = {}
    rows = [emp("10000000", "A"), emp("20000000", "B LTDA"), emp("30000000", "C SA", porte="05"), emp("40000000", "D")]
    J.fill_companies(rows, wanted, stats, stop_after="30000000")
    assert wanted["20000000"]["razao_social"] == "B LTDA" and wanted["30000000"]["porte"] == "DEMAIS"
    assert wanted["20000000"]["capital_social"] == 150000.0 and stats["early_stop"] == 1


def test_unordered_file_is_reread_instead_of_losing_records():
    rows = [emp("10000000", "A"), emp("30000000", "fora de ordem"), emp("20000000", "PROCURADA LTDA")]
    by = {"20000000": {}}
    stats = {}
    J.fill_with_fallback(lambda: iter(rows), by, ["20000000"], stats)
    assert by["20000000"]["razao_social"] == "PROCURADA LTDA"
    assert stats["full_rereads"] == 1 and stats["not_found"] == 0


def test_plan_company_parts():
    plan = J.plan_company_parts({1: "00000000", 2: "04631961", 0: "41273589"}, ["00000001", "05000000", "50000000"])
    assert plan == {1: ["00000001"], 2: ["05000000"], 0: ["50000000"]}


# ---------------------------------------------- servidor WebDAV simulado
@pytest.fixture
def fake_rfb(monkeypatch):
    files = {
        "Cnaes.zip": zipped([["6491300", "Sociedades de fomento mercantil - factoring"], ["8513900", "Ensino fundamental"]]),
        "Municipios.zip": zipped([["0255", "MANAUS"]]),
        "Naturezas.zip": zipped([["2062", "Sociedade Empresária Limitada"]]),
        "Estabelecimentos0.zip": zipped([est("11111111", "6491300", fantasia="FOMENTO A"), est("55555555", "4711302")]),
        "Estabelecimentos1.zip": zipped([est("66666666", "8513900", fantasia="ESCOLA Ç")]),
        "Empresas1.zip": zipped([emp("00000001", "X"), emp("11111111", "FOMENTO A LTDA", porte="05"), emp("12000000", "Y")]),
        "Empresas0.zip": zipped([emp("50000000", "Z"), emp("66666666", "ESCOLA ÇÃO LTDA", porte="01")]),
    }
    for i in range(2, 10):
        files[f"Empresas{i}.zip"] = zipped([emp(f"{90000000 + i}", "VAZIO")])
    files["Empresas0.zip"] = zipped([emp("50000000", "Z"), emp("66666666", "ESCOLA ÇÃO LTDA", porte="01")])
    ranges = []

    def handler(req):
        path = req.url.path
        if req.method == "PROPFIND":
            body = "".join(f"<d:response><d:href>/public.php/webdav/Dados/Cadastros/CNPJ/{m}/</d:href></d:response>"
                           for m in ["2026-09", "2026-10"])
            return httpx.Response(207, text=f"<d:multistatus>{body}</d:multistatus>")
        name = path.rsplit("/", 1)[-1]
        data = files[name]
        m = re.match(r"bytes=(\d+)-(\d+)", req.headers["range"])
        a, b = int(m.group(1)), min(int(m.group(2)), len(data) - 1)
        ranges.append((name, a, b))
        return httpx.Response(206, content=data[a:b + 1], headers={"Content-Range": f"bytes {a}-{b}/{len(data)}"})

    monkeypatch.setattr(R, "client", lambda timeout=60.0: httpx.Client(transport=httpx.MockTransport(handler)))
    # Empresas1 começa em 00000001 e Empresas0 em 50000000 → 66666666 vai para o 0
    return ranges


def test_range_file_never_probes_single_byte(fake_rfb):
    with R.client() as h:
        rows = list(R.iter_remote_rows("2026-10", "Cnaes.zip", h))
    assert rows[0][0] == "6491300"
    assert all(b - a > 0 for _, a, b in fake_rfb)  # o servidor real trava com bytes=0-0


def test_job_end_to_end(fake_rfb):
    recs = J.main(["--segments", "credito_fomento,educacao_privada", "--uf", "AM", "--parts", "0-1"])
    by = {r["cnpj_basico"]: r for r in recs}
    assert set(by) == {"11111111", "66666666"}
    assert by["11111111"]["razao_social"] == "FOMENTO A LTDA" and by["11111111"]["porte"] == "DEMAIS"
    assert by["66666666"]["razao_social"] == "ESCOLA ÇÃO LTDA"  # latin-1 preservado
    assert by["11111111"]["natureza_juridica"] == "Sociedade Empresária Limitada"
    assert by["11111111"]["municipio"] == "MANAUS" and by["11111111"]["cnae_descricao"].startswith("Sociedades")
    from app.db.database import SessionLocal
    from app.db.models import Company
    db = SessionLocal()
    c = db.query(Company).filter_by(cnpj="11111111000100").one()
    assert c.target_profile == "credito_fomento" and c.registry_source.startswith("Receita Federal")
    assert c.institutional_email is None
    db.close()
    again = J.main(["--segments", "credito_fomento", "--uf", "AM", "--parts", "0", "--min-size", "05"])
    assert [r["cnpj_basico"] for r in again] == ["11111111"]


def test_job_reads_local_zip_folder(tmp_path, fake_rfb):
    rel = tmp_path / "2026-10"; rel.mkdir()
    (rel / "Cnaes.zip").write_bytes(zipped([["6491300", "Factoring"]]))
    (rel / "Municipios.zip").write_bytes(zipped([["0255", "MANAUS"]]))
    (rel / "Naturezas.zip").write_bytes(zipped([["2062", "LTDA"]]))
    (rel / "Estabelecimentos0.zip").write_bytes(zipped([est("77777777", "6491300")]))
    (rel / "Empresas1.zip").write_bytes(zipped([emp("00000001", "X"), emp("77777777", "LOCAL FOMENTO LTDA")]))
    before = len(fake_rfb)
    recs = J.main(["--local-dir", str(tmp_path), "--release", "2026-10", "--segments", "credito_fomento", "--parts", "0", "--dry-run"])
    assert recs[0]["razao_social"] == "LOCAL FOMENTO LTDA" and recs[0]["municipio"] == "MANAUS"
    assert len(fake_rfb) == before  # nenhuma leitura remota


def test_local_dir_requires_release(tmp_path):
    with pytest.raises(SystemExit):
        J.main(["--local-dir", str(tmp_path)])


def test_reprofile_updates_profiles_when_rules_change():
    from app.db.database import SessionLocal, ensure_schema
    from app.db.models import Company
    ensure_schema()
    db = SessionLocal()
    db.add(Company(name="REPRESENTANTE LTDA", cnpj="99999999000199", cnae_main="4611700", target_profile="atacado"))
    db.add(Company(name="ATACADISTA LTDA", cnpj="99999998000199", cnae_main="4623199", target_profile="atacado"))
    db.commit()
    assert J.reprofile(db) >= 1
    by = {c.cnpj: c.target_profile for c in db.query(Company).filter(Company.cnpj.in_(["99999999000199", "99999998000199"]))}
    assert by == {"99999999000199": "representacao_comercial", "99999998000199": "atacado"}
    db.close()


def test_individual_policy_excludes_or_masks_cpf():
    recs = [{"natureza_codigo": "2135", "razao_social": "FULANO DE TAL 12345678901"},
            {"natureza_codigo": "2062", "razao_social": "LOJA DO BAIRRO LTDA"}]
    stats = {}
    assert [r["razao_social"] for r in J.apply_individual_policy([dict(r) for r in recs], False, stats)] == ["LOJA DO BAIRRO LTDA"]
    assert stats["individuals"] == 1
    kept = J.apply_individual_policy([dict(r) for r in recs], True, {})
    assert kept[0]["razao_social"] == "FULANO DE TAL" and kept[0]["individual"] is True
    assert "12345678901" not in str(kept)


def test_all_sectors_by_default_and_individuals_excluded(fake_rfb):
    recs = J.main(["--uf", "AM", "--parts", "0-1", "--dry-run"])
    assert {r["cnpj_basico"] for r in recs} == {"11111111", "55555555", "66666666"}   # varejo (55555555) agora entra
    assert next(r for r in recs if r["cnpj_basico"] == "55555555")["target_profile"] == "varejo"


def test_skip_companies_requires_explicit_individual_decision():
    with pytest.raises(SystemExit):
        J.main(["--skip-companies", "--parts", "1", "--dry-run"])


def test_max_records_guard(fake_rfb):
    with pytest.raises(SystemExit):
        J.main(["--uf", "AM", "--parts", "0-1", "--max-records", "1", "--dry-run"])


def test_checkpoint_resumes_without_rereading_parts(tmp_path, fake_rfb):
    ck = tmp_path / "am.ckpt.json"
    args = ["--segments", "credito_fomento,educacao_privada", "--uf", "AM", "--parts", "0-1", "--dry-run", "--checkpoint", str(ck)]
    first = J.main(args)
    assert ck.exists() and len(first) == 2
    reads_before = sum(1 for n, *_ in fake_rfb if n.startswith("Estabelecimentos"))
    again = J.main(args)   # simula a retomada: os dois arquivos já constam do checkpoint
    reads_after = sum(1 for n, *_ in fake_rfb if n.startswith("Estabelecimentos"))
    assert reads_after == reads_before and {r["cnpj_basico"] for r in again} == {r["cnpj_basico"] for r in first}
