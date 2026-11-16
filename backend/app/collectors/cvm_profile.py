"""CVM open-company profile source.

Only corporate registry fields are retained. This source describes who the
company is (perfil), never recent commercial intent.
"""
from __future__ import annotations

import csv
import io
import re

import httpx

URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
USER_AGENT = "LeadCobAI/0.5.3 (dados abertos CVM)"


def clean_cnpj(value: str | None) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    return digits if len(digits) == 14 else None


def parse_csv(content: bytes) -> list[dict]:
    text = content.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    required = {"CNPJ_CIA", "DENOM_SOCIAL", "SIT"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise ValueError("Formato CVM inesperado: colunas cadastrais obrigatórias ausentes.")
    rows = []
    for raw in reader:
        cnpj = clean_cnpj(raw.get("CNPJ_CIA"))
        if not cnpj:
            continue
        rows.append({
            "cnpj": cnpj,
            "name": (raw.get("DENOM_SOCIAL") or "").strip(),
            "registry_status": (raw.get("SIT") or "").strip(),
            "cvm_code": (raw.get("CD_CVM") or "").strip() or None,
            "profile_key": "companhia_aberta",
            "source_name": "CVM — Companhias Abertas",
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
