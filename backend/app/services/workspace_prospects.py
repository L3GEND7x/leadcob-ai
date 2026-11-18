"""No legacy Company or contact directory access."""
from datetime import datetime, timezone
import httpx
from fastapi import HTTPException
from app.collectors import cnpj_api
from app.services.cnpj import clean_cnpj, is_valid_cnpj
from app.db.models import WorkspaceSuppression
from app.core.account_access import authorize
from app.services.commercial_entitlements import check_subscription


def lookup(db, token, organization_id, cnpj):
    principal = authorize(db, token, organization_id, "read")
    scope = principal.organization_id
    check_subscription(db, scope)
    key = clean_cnpj(cnpj)
    if not is_valid_cnpj(key):
        raise HTTPException(422, "CNPJ inválido.")
    if db.get(WorkspaceSuppression, (scope,key)):
        raise HTTPException(409, "Empresa suprimida nesta organização.")
    try:
        with httpx.Client(timeout=8, trust_env=False, follow_redirects=False) as client:
            data = cnpj_api.lookup(key,http=client,attempts=1,pause=0)
    except cnpj_api.CNPJNotFound:
        raise HTTPException(404,"CNPJ não localizado nas fontes consultadas.")
    except cnpj_api.CNPJInvalid:
        raise HTTPException(422,"Consulta cadastral recusada.")
    except cnpj_api.CNPJUnavailable:
        raise HTTPException(502,"Fontes cadastrais indisponíveis.")
    # Conservative: unknown nature or individual/MEI excluded, including potential name/CPF.
    nature = str(data.get("natureza_juridica") or "").strip()
    if not nature or data.get("opcao_mei") is True or "individual" in nature.casefold() or nature.startswith(("213","2.1.3")):
        raise HTTPException(422,"Natureza jurídica não elegível ou não confirmada.")
    db.expire_all()
    authorize(db, token, scope,"read")
    check_subscription(db,scope)
    if db.get(WorkspaceSuppression,(scope,key)):
        raise HTTPException(409,"Empresa suprimida nesta organização.")
    return {k:data.get(k) for k in ("cnpj","razao_social","municipio","uf","cnae_principal","situacao_cadastral","source")} | {
        "observed_at":datetime.now(timezone.utc).isoformat(),
        "note":"Consulta cadastral pública; não comprova demanda nem disponibilidade de contatos."
    }
