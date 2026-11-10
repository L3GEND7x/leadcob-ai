from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.db.database import SessionLocal,ensure_schema
from app.db.models import AuditLog,Company,Opportunity
from app.api.routes import router
from app.api.routes_crm import router as crm_router
from app.api.routes_stage2 import router as stage2_router
from app.api.routes_reports import router as reports_router
from app.services.scoring import score_opportunity
from app.core.security import router as auth_router, access_middleware, validate_configuration
app=FastAPI(title=settings.app_name,version="0.5.3",description="Inteligência comercial B2B para oportunidades de cobrança.")
from app.api.routes_contacts import router as contacts_router
app.middleware("http")(access_middleware)
app.include_router(auth_router)
from app.api.routes_assistant import router as assistant_router
app.include_router(assistant_router)
app.include_router(contacts_router)
app.include_router(crm_router)
app.include_router(stage2_router)
app.include_router(reports_router)
app.include_router(router)
frontend=Path(__file__).resolve().parents[2]/"frontend"
app.mount("/static",StaticFiles(directory=str(frontend)),name="static")
DEMO_SOURCE="Demonstração"
def remove_demo(db):
    """Remove os exemplos fictícios das versões antigas (fonte 'Demonstração') que não foram trabalhados no CRM."""
    demo=db.query(Opportunity).filter(Opportunity.source_name==DEMO_SOURCE).all()
    if not demo: return 0
    ids={o.company_id for o in demo}
    for o in demo: db.delete(o)
    db.flush()
    for c in db.query(Company).filter(Company.id.in_(ids)).all():
        if not c.opportunities and not c.interactions and not c.tasks and not c.pipeline_stage and not c.cnpj: db.delete(c)
    db.add(AuditLog(event="demo_removed",entity_type="opportunity",entity_id=None,details={"opportunities":len(demo)}))
    db.commit(); return len(demo)
def seed():
    db=SessionLocal()
    try:
        if not settings.demo_seed:
            remove_demo(db); return
        if db.query(Opportunity).count()==0:
            rows=[("Atacado Norte Distribuição","Atacado e distribuição","Manaus","AM","hiring","Analista de cobrança — carteira B2B","Vaga demonstrativa para cobrança, negociação e contas a receber.","Exemplo fictício de evidência; substituir por fonte real antes de prospectar.","Demonstração","https://www.linkedin.com/jobs/"),("Indústria Vale Verde","Indústria","Belém","PA","outsourcing","Sinal de possível demanda — recuperação de crédito","Sinal demonstrativo de revisão de recebíveis; não confirma intenção de terceirizar.","Exemplo fictício. Terceirização depende de confirmação direta.","Demonstração","https://www.gov.br/pncp/"),("Comercial Centro-Oeste","Comércio atacadista","Goiânia","GO","hiring","Assistente de contas a receber","Vaga demonstrativa para contas a receber e acompanhamento de títulos.","Exemplo fictício de evidência; não é lead real.","Demonstração","https://www.gov.br/receitafederal/")]
            for name,seg,city,uf,kind,title,desc,evidence,src,url in rows:
                c=Company(name=name,segment=seg,city=city,state=uf); db.add(c); db.flush(); score,reason=score_opportunity(kind,desc,evidence,url)
                db.add(Opportunity(company_id=c.id,kind=kind,title=title,description=desc,evidence=evidence,source_name=src,source_url=url,score=score,score_reason=reason,status="review",confidence=0.2,is_verified=False))
            db.commit()
    finally: db.close()
@app.on_event("startup")
def startup():
    validate_configuration()
    ensure_schema()
    seed()
@app.get("/")
def dashboard(): return FileResponse(frontend/"index.html")
