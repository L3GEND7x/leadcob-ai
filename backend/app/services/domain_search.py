"""Search results are candidates; a CNPJ on the actual site is stronger evidence."""
import re
import time
from urllib.parse import urlparse

import httpx

from app.collectors.site_contacts import _root
from app.services.safe_http import public_client, bounded_get, validate_url

BLOCKED = {'google.com', 'instagram.com', 'facebook.com', 'linkedin.com', 'jusbrasil.com.br',
           'econodata.com.br', 'cnpj.biz', 'consultacnpj.com', 'receita.fazenda.gov.br',
           'gov.br', 'youtube.com', 'reclameaqui.com.br'}


def search(company, api_key):
    query = f'"{company.cnpj}" "{company.name}" site oficial' if company.cnpj else f'"{company.name}" site oficial {company.city or ""}'
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
        response = client.get('https://api.search.brave.com/res/v1/web/search',
            params={'q': query[:600], 'count': 8, 'country': 'BR', 'search_lang': 'pt'},
            headers={'X-Subscription-Token': api_key})
        response.raise_for_status()
        hits = response.json().get('web', {}).get('results', [])[:8]
    found = {}
    for hit in hits:
        url = hit.get('url') or ''
        try:
            parsed = validate_url(url)
            root = _root(parsed.hostname)
            if root in BLOCKED or root.endswith('.gov.br') or root in found:
                continue
            website = f'https://{parsed.hostname}'
            # The returned search snippet is not evidence that this is the company's own site.
            evidence = 'Resultado da busca. Confirme se o domínio pertence à empresa.'
            if company.cnpj:
                with public_client() as client:
                    page = bounded_get(client, website, parsed.hostname, time.monotonic() + 12, max_bytes=200_000)
                    digits = re.sub(r'\D', '', page.text)
                    if page.status_code == 200 and company.cnpj in digits:
                        evidence = f'CNPJ {company.cnpj} encontrado na página inicial do domínio.'
            found[root] = {'website': website, 'source_url': url, 'evidence': evidence,
                           'status': 'cnpj_no_site' if evidence.startswith('CNPJ ') else 'a_verificar'}
        except (ValueError, httpx.HTTPError):
            continue
        if len(found) >= 5:
            break
    return list(found.values())
