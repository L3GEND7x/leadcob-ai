"""One-time, idempotent import of the reviewed AM CNPJ snapshot into Railway.

Run in a separate Railway service using the app image, DATABASE_URL referencing
Postgres, and start command: python -m app.jobs.import_railway_snapshot
"""
import json
import re
from datetime import datetime

import httpx

from app.db.database import SessionLocal, check_schema_revision
from app.db.models import Company, Suppression

SOURCE_REVISION = 'c207b097e339d4e0c8dcc62f8468d46f8edd1d24'
SOURCE_URL = (f'https://raw.githubusercontent.com/L3GEND7x/leadcob-ai/'
              f'{SOURCE_REVISION}/bases/AM.json')
MAX_BYTES = 50_000_000
MAX_ROWS = 50_000
TEXT_FIELDS = {
    'trade_name': 220, 'segment': 120, 'city': 100, 'cnae_main': 7,
    'cnae_desc': 255, 'cnae_secondary': 2000, 'registration_status': 30,
    'company_size': 40, 'legal_nature': 160, 'opened_at': 10, 'target_profile': 40,
}


def fetch_snapshot(client):
    with client.stream('GET', SOURCE_URL) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError('Snapshot excede o limite de 50 MB.')
            chunks.append(chunk)
    return json.loads(b''.join(chunks))


def validated_rows(snapshot):
    rows = snapshot.get('empresas') if isinstance(snapshot, dict) else None
    if not isinstance(rows, list) or not 0 < len(rows) <= MAX_ROWS:
        raise ValueError('Snapshot sem lista de empresas válida.')
    generated_at = datetime.fromisoformat(snapshot['gerado_em'])
    if generated_at.tzinfo is None:
        raise ValueError('Snapshot sem data com fuso horário.')
    seen, validated = set(), []
    for position, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f'Registro {position} inválido.')
        cnpj, name = row.get('cnpj'), row.get('name')
        if (not isinstance(cnpj, str) or not re.fullmatch(r'[A-Z0-9]{14}', cnpj)
                or not isinstance(name, str) or not name.strip() or row.get('state') != 'AM'):
            raise ValueError(f'Registro {position} não é uma empresa AM válida.')
        if cnpj in seen:
            raise ValueError(f'CNPJ duplicado no registro {position}.')
        seen.add(cnpj)
        data = {'cnpj': cnpj, 'name': name[:220], 'state': 'AM',
                'registry_source': f'Receita Federal — snapshot AM {generated_at.date()}',
                'registry_updated_at': generated_at}
        for key, length in TEXT_FIELDS.items():
            value = row.get(key)
            if value is not None:
                if not isinstance(value, str):
                    raise ValueError(f'Campo {key} inválido no registro {position}.')
                data[key] = value[:length]
        capital = row.get('capital_social')
        if capital is not None:
            if type(capital) not in (int, float) or not 0 <= capital < 1e15:
                raise ValueError(f'Capital inválido no registro {position}.')
            data['capital_social'] = capital
        validated.append(data)
    return generated_at, validated


def import_rows(db, rows, batch_size=500):
    created = existing = suppressed = 0
    for offset in range(0, len(rows), batch_size):
        batch = rows[offset:offset + batch_size]
        keys = [row['cnpj'] for row in batch]
        present = {cnpj for (cnpj,) in db.query(Company.cnpj).filter(Company.cnpj.in_(keys)).all()}
        blocked = {cnpj for (cnpj,) in db.query(Suppression.cnpj).filter(Suppression.cnpj.in_(keys)).all()}
        new = [Company(**row) for row in batch if row['cnpj'] not in present | blocked]
        db.add_all(new)
        db.commit()
        created += len(new)
        existing += len(present)
        suppressed += len(blocked - present)
    return {'created': created, 'existing': existing, 'suppressed': suppressed}


def main():
    check_schema_revision()
    with httpx.Client(timeout=120, follow_redirects=False) as client:
        generated_at, rows = validated_rows(fetch_snapshot(client))
    with SessionLocal() as db:
        result = import_rows(db, rows)
    print(f'Snapshot AM {generated_at.date()}: {len(rows)} registros; '
          f'{result["created"]} inseridos, {result["existing"]} existentes, '
          f'{result["suppressed"]} suprimidos.', flush=True)


if __name__ == '__main__':
    main()
