"""ANS active-operator profile source.

Only corporate fields needed for profile are retained. Published contact and
representative fields are deliberately ignored because LeadCob prospecting must
not ingest personal contact data from registry datasets.
"""
from __future__ import annotations

import csv
import io
import re

import httpx

URL = "https://dadosabertos.ans.gov.br/FTP/PDA/operadoras_de_plano_de_saude_ativas/Relatorio_cadop.csv"
USER_AGENT = "LeadCobAI/0.5.3 (dados abertos ANS)"


def clean_cnpj(value: str | None) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    return digits if len(digits) == 14 else None


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Não foi possível decodificar o CSV da ANS.")


def parse_csv(content: bytes) -> list[dict]:
    reader = csv.DictReader(io.StringIO(_decode(content)), delimiter=";")
    required = {"Registro_ANS", "CNPJ", "Razao_Social", "Modalidade"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise ValueError("Formato ANS inesperado: colunas cadastrais obrigatórias ausentes.")
    rows = []
    for raw in reader:
        cnpj = clean_cnpj(raw.get("CNPJ"))
        if not cnpj:
            continue
        rows.append({
            "cnpj": cnpj,
            "name": (raw.get("Razao_Social") or "").strip(),
            "trade_name": (raw.get("Nome_Fantasia") or "").strip() or None,
            "ans_registry": (raw.get("Registro_ANS") or "").strip() or None,
            "modality": (raw.get("Modalidade") or "").strip() or None,
            "city": (raw.get("Cidade") or "").strip() or None,
            "state": (raw.get("UF") or "").strip().upper() or None,
            "registered_at": (raw.get("Data_Registro_ANS") or "").strip() or None,
            "profile_key": "planos_seguros",
            "source_name": "ANS — Operadoras ativas",
            "source_url": URL,
        })
    return rows


def fetch(client: httpx.Client | None = None) -> list[dict]:
    own = client is None
    client = client or httpx.Client(timeout=45.0, headers={"User-Agent": USER_AGENT})
    try:
        response = client.get(URL)
        response.raise_for_status()
        return parse_csv(response.content)
    finally:
        if own:
            client.close()


__all__ = ["fetch", "parse_csv", "clean_cnpj", "URL"]
