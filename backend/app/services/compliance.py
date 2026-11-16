"""Consulta CEIS/CNEP para alerta de conformidade empresarial.

Somente CNPJ de pessoa jurídica. Nenhum resultado é tratado como prova de
inadimplência. A chave fica em PORTAL_TRANSPARENCIA_API_KEY.
"""
from __future__ import annotations

import re

import httpx

from app.core.config import settings

BASE_URL = "https://api.portaldatransparencia.gov.br/api-de-dados"


class ComplianceUnavailable(RuntimeError):
    pass


def clean_cnpj(value: str) -> str:
    cnpj = re.sub(r"\D", "", value or "")
    if len(cnpj) != 14:
        raise ValueError("CNPJ inválido para consulta de conformidade.")
    return cnpj


def _summary(source: str, row: dict) -> dict:
    sanctioned = row.get("sancionado") or {}
    person = row.get("pessoa") or {}
    sanction = row.get("tipoSancao") or {}
    org = row.get("orgaoSancionador") or {}
    return {
        "source": source,
        "id": row.get("id"),
        "sanction_type": sanction.get("descricao") or sanction.get("descricaoResumida") or None,
        "sanctioning_body": org.get("nome") or org.get("nomeOrgaoSancionador") or None,
        "start_date": row.get("dataInicioSancao"),
        "end_date": row.get("dataFimSancao"),
        "publication_date": row.get("dataPublicacaoSancao"),
        "process_number": row.get("numeroProcesso"),
        "publication_url": row.get("linkPublicacao"),
        "sanctioned_name": sanctioned.get("nome") or person.get("nome") or None,
    }


def _fetch(client: httpx.Client, endpoint: str, cnpj: str) -> list[dict]:
    response = client.get(
        f"{BASE_URL}/{endpoint}",
        params={"codigoSancionado": cnpj, "pagina": 1},
        headers={"Accept": "application/json", "chave-api-dados": settings.portal_transparencia_api_key},
    )
    if response.status_code in (401, 403):
        raise ComplianceUnavailable("Chave do Portal da Transparência ausente, inválida ou sem autorização.")
    if response.status_code == 429 or response.status_code >= 500:
        raise ComplianceUnavailable(f"Portal da Transparência indisponível (HTTP {response.status_code}).")
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise ComplianceUnavailable("Formato inesperado da API do Portal da Transparência.")
    return data


def check_company(cnpj: str, client: httpx.Client | None = None) -> dict:
    cnpj = clean_cnpj(cnpj)
    if not settings.portal_transparencia_api_key:
        return {
            "configured": False,
            "cnpj": cnpj,
            "has_records": None,
            "records": [],
            "note": "Chave do Portal da Transparência não configurada.",
        }

    own = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        records = []
        for endpoint, source in (("ceis", "CEIS"), ("cnep", "CNEP")):
            for row in _fetch(client, endpoint, cnpj):
                # A API admite CPF ou CNPJ, mas a consulta do LeadCob envia somente CNPJ PJ.
                records.append(_summary(source, row))
        return {
            "configured": True,
            "cnpj": cnpj,
            "has_records": bool(records),
            "records": records,
            "note": (
                "Alerta de conformidade baseado em registros públicos CEIS/CNEP. "
                "Não é prova de inadimplência, risco de crédito ou impedimento comercial atual."
            ),
        }
    finally:
        if own:
            client.close()


__all__ = ["check_company", "ComplianceUnavailable", "clean_cnpj"]
