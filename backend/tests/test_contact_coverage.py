from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.database import Base
from app.db.models import Company, BusinessContact, Suppression
from app.api.routes_contacts import contact_coverage


def test_coverage_counts_distinct_companies():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        a,b,c,d,e = [Company(name=name,city=city,state=uf) for name,city,uf in [
            ('A','Manaus','AM'),('B','Manaus','AM'),('C','Manaus','AM'),
            ('D','Belém','PA'),('E','Manaus','AM')]]
        db.add_all([a,b,c,d,e])
        db.flush()
        db.add(Suppression(company_id=c.id,reason='Opt-out'))
        def add(company,kind,value,status):
            db.add(BusinessContact(company_id=company.id,kind=kind,value=value,
                                   status=status,source_name='Test source'))
        add(a,'email','financeiro@example.org','verificado')
        add(a,'email','contato@example.org','a_verificar')
        add(a,'phone','92999999999','a_verificar')
        add(b,'email','contato@example.net','invalido')
        add(c,'email','contato@example.com','verificado')
        add(d,'linkedin','https://www.linkedin.com/company/example','verificado')
        add(e,'email','anon:removed','verificado')
        db.commit()
        r=contact_coverage(uf='am',city='manaus',db=db)
        assert r['eligible_company_records']==3
        assert r['with_any_channel']==1
        assert r['without_registered_channel']==2
        assert r['with_any_verified_channel']==1
        assert r['channels']['email']=={'available':1,'verified':1}
        assert r['channels']['phone']=={'available':1,'verified':0}
        assert r['channels']['linkedin']=={'available':0,'verified':0}
        assert contact_coverage(uf='',city='',db=db)['with_any_channel']==2
        assert contact_coverage(uf='RR',city='',db=db)['eligible_company_records']==0
    engine.dispose()
