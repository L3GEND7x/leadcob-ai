from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import Company, BusinessContact, Suppression
from app.api.routes_contacts import BatchDiscoveryIn, discover_batch
from app.collectors import site_contacts


def test_batch_discovery(monkeypatch):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    calls = []
    def discover(website, max_pages):
        calls.append(website)
        assert max_pages == 2
        if 'fail' in website:
            raise ValueError('unavailable')
        email = {'email':'financeiro@example.org', 'source_url':'https://example.org/contato'}
        return dict(emails=[email,email], channels=[], pages_read=['https://example.org'])
    monkeypatch.setattr(site_contacts,'discover',discover)
    with Session(engine) as db:
        a = Company(name='A', cnpj='12345678000195', website='https://example.org')
        b = Company(name='B', cnpj='11222333000181', website='https://blocked.example.org')
        c = Company(name='C', cnpj='04252011000110', website='https://fail.example.org')
        db.add_all([a,b,c])
        db.flush()
        ids = [a.id,b.id,c.id]
        db.add(Suppression(company_id=b.id, cnpj=b.cnpj, reason='Opt-out'))
        db.commit()
        result = discover_batch(BatchDiscoveryIn(company_ids=[ids[0],ids[0],ids[1],ids[2],999999]),db)
        assert result['processed'] == 4
        assert result['added'] == 1
        assert [r['status'] for r in result['items']] == ['completed','suppressed','unavailable','not_found']
        assert calls == ['https://example.org','https://fail.example.org']
        contact = db.query(BusinessContact).one()
        assert contact.status == 'a_verificar'
        assert contact.source_url == 'https://example.org/contato'
        assert discover_batch(BatchDiscoveryIn(company_ids=[ids[0]]),db)['added'] == 0
    engine.dispose()
