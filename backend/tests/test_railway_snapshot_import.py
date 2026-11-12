import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import Company, Suppression
from app.jobs.import_railway_snapshot import import_rows, validated_rows


def sample(cnpj, **kwargs):
    return {'cnpj': cnpj, 'name': 'Empresa de teste', 'state': 'AM',
            'institutional_email': 'pessoal@example.org', **kwargs}


def test_snapshot_validation_excludes_unapproved_fields():
    stamp, rows = validated_rows({'gerado_em': '2026-11-10T22:00:00+00:00',
                                  'empresas': [sample('12345678000190', capital_social=1000.0)]})
    assert stamp.year == 2026
    assert rows[0]['capital_social'] == 1000.0
    assert 'institutional_email' not in rows[0]
    with pytest.raises(ValueError, match='CNPJ duplicado'):
        validated_rows({'gerado_em': '2026-11-10T22:00:00+00:00',
                        'empresas': [sample('12345678000190'), sample('12345678000190')]})
    with pytest.raises(ValueError, match='empresa AM válida'):
        validated_rows({'gerado_em': '2026-11-10T22:00:00+00:00',
                        'empresas': [sample('12345678000190', state='PA')]})


def test_import_is_idempotent_and_preserves_existing_crm_and_suppression():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add(Company(cnpj='12345678000190', name='Cadastro manual', pipeline_stage='qualificada'))
            db.add(Suppression(cnpj='12345678000191', reason='Não contatar'))
            db.commit()
            _, rows = validated_rows({'gerado_em': '2026-11-10T22:00:00+00:00', 'empresas': [
                sample('12345678000190'), sample('12345678000191'), sample('12345678000192')]})
            assert import_rows(db, rows, batch_size=2) == {'created': 1, 'existing': 1, 'suppressed': 1}
            assert import_rows(db, rows, batch_size=2) == {'created': 0, 'existing': 2, 'suppressed': 1}
            manual = db.query(Company).filter_by(cnpj='12345678000190').one()
            assert manual.name == 'Cadastro manual' and manual.pipeline_stage == 'qualificada'
            assert db.query(Company).filter_by(cnpj='12345678000191').count() == 0
            assert db.query(Company).filter_by(cnpj='12345678000192').count() == 1
    finally:
        engine.dispose()
