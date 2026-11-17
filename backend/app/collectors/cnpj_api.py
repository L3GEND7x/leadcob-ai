"""Consulta individual de CNPJ: BrasilAPI (principal) e Minha Receita (reserva).

Ambas publicam os dados abertos da Receita Federal com o mesmo esquema
(verificado em 09/11/2026). Defasagem: refletem a última publicação mensal da
Receita, não o cadastro em tempo real.
"""
from __future__ import annotations

import os
import time

import httpx

from app.services.cnpj import clean_cnpj, is_valid_cnpj, normalize_api

PROVIDERS = [
    ("BrasilAPI", os.getenv("BRASILAPI_URL", "https://brasilapi.com.br/api/cnpj/v1/{cnpj}")),
    ("Minha Receita", os.getenv("MINHARECEITA_URL", "https://minhareceita.org/{cnpj}")),
]


class CNPJInvalid(ValueError):
    pass


class CNPJNotFound(LookupError):
    pass


class CNPJUnavailable(RuntimeError):
    pass


def lookup(cnpj: str, http: httpx.Client | None = None, attempts: int = 2, pause: float = 1.5) -> dict:
    c = clean_cnpj(cnpj)
    if not is_valid_cnpj(c):
        raise CNPJInvalid(f"CNPJ inválido: {cnpj}")
    own = http is None
    http = http or httpx.Client(timeout=20.0, headers={"User-Agent": "LeadCobAI/0.3", "Accept": "application/json"})
    errors = []
    try:
        for name, template in PROVIDERS:
            for i in range(attempts):
                try:
                    r = http.get(template.format(cnpj=c))
                except httpx.TransportError as exc:
                    errors.append(f"{name}: {type(exc).__name__}")
                    time.sleep(pause * (i + 1)); continue
                if r.status_code == 200:
                    try:
                        data = normalize_api(r.json(), source=name)
                        if data["cnpj"] != c or not data.get("razao_social"):
                            raise ValueError("Unexpected registry identity")
                    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
                        errors.append(f"{name}: resposta cadastral inválida")
                        break
                    return data
                if r.status_code == 404:
                    errors.append(f"{name}: HTTP 404")
                    break
                if r.status_code == 400:
                    raise CNPJInvalid(r.json().get("message", "CNPJ inválido"))
                errors.append(f"{name}: HTTP {r.status_code}")
                if r.status_code == 429 or r.status_code >= 500:
                    time.sleep(pause * (i + 1)); continue
                break
    finally:
        if own:
            http.close()
    if len(errors) == len(PROVIDERS) and all(e.endswith("HTTP 404") for e in errors):
        raise CNPJNotFound("CNPJ não encontrado nas fontes consultadas.")
    raise CNPJUnavailable("; ".join(errors) or "sem resposta")
