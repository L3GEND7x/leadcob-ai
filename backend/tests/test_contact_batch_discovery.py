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
        a = Company(name='A', registration_status='ATIVA', legal_nature='Sociedade Empresária Limitada', cnpj='12345678000195', website='https://example.org')
        b = Company(name='B', registration_status='ATIVA', legal_nature='Sociedade Empresária Limitada', cnpj='11222333000181', website='https://blocked.example.org')
        c = Company(name='C', registration_status='ATIVA', legal_nature='Sociedade Empresária Limitada', cnpj='04252011000110', website='https://fail.example.org')
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


def test_batch_rechecks_corporate_eligibility_before_and_after_network(monkeypatch):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    calls = []
    with Session(engine) as db:
        common = dict(website='https://example.org', registration_status='ATIVA',
                      legal_nature='Sociedade Empresária Limitada')
        a = Company(name='Inativa', cnpj='12345678000195', website='https://example.org',
                    registration_status='BAIXADA', legal_nature='Sociedade Empresária Limitada')
        b = Company(name='Individual', cnpj='11222333000181', website='https://example.org',
                    registration_status='ATIVA', legal_nature='2135 Empresário Individual')
        c = Company(name='Concorrente', cnpj='04252011000110', cnae_main='8291100', **common)
        db.add_all([a,b,c]); db.commit()
        ids = [a.id,b.id,c.id]
        monkeypatch.setattr(site_contacts,'discover',lambda *args,**kw: calls.append(args))
        result = discover_batch(BatchDiscoveryIn(company_ids=ids),db)
        assert [r['status'] for r in result['items']] == ['ineligible_registry','ineligible_registry','competitor']
        assert not calls and result['added'] == 0
        a.registration_status = 'ATIVA'; db.commit()
        duplicate = Company(name='Duplicata',cnpj=a.cnpj,website='https://other.example.org',
                            registration_status='ATIVA',legal_nature='Sociedade Empresária Limitada')
        db.add(duplicate);db.commit()
        assert discover_batch(BatchDiscoveryIn(company_ids=[a.id]),db)['items'][0]['status'] == 'conflicting_site'
        assert not calls
        duplicate.website = a.website;db.commit()
        def changes_while_fetching(website, max_pages):
            calls.append(website)
            duplicate.registration_status='BAIXADA'
            db.commit()
            return dict(emails=[{'email':'financeiro@example.org','source_url':'https://example.org'}],
                        channels=[],pages_read=['https://example.org'])
        monkeypatch.setattr(site_contacts,'discover',changes_while_fetching)
        result=discover_batch(BatchDiscoveryIn(company_ids=[a.id]),db)
        assert result['items'][0]['status']=='changed_or_suppressed'
        assert result['added']==0 and db.query(BusinessContact).count()==0
    engine.dispose()
