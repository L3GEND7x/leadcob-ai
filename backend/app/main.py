from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.db.database import SessionLocal,ensure_schema
from app.db.models import Company,Opportunity
from app.api.routes import router
from app.services.scoring import score_opportunity
app=FastAPI(title=settings.app_name,version="0.2.1",description="Inteligência comercial B2B para oportunidades de cobrança.")
app.include_router(router)
frontend=Path(__file__).resolve().parents[2]/"frontend"
app.mount("/static",StaticFiles(directory=str(frontend)),name="static")
def seed():
    db=SessionLocal()
    try:
        if db.query(Opportunity).count()==0:
            rows=[("Atacado Norte Distribuição","Atacado e distribuição","Manaus","AM","hiring","Analista de cobrança — carteira B2B","Vaga demonstrativa para cobrança, negociação e contas a receber.","Exemplo fictício de evidência; substituir por fonte real antes de prospectar.","Demonstração","https://www.linkedin.com/jobs/"),("Indústria Vale Verde","Indústria","Belém","PA","outsourcing","Sinal de possível demanda — recuperação de crédito","Sinal demonstrativo de revisão de recebíveis; não confirma intenção de terceirizar.","Exemplo fictício. Terceirização depende de confirmação direta.","Demonstração","https://www.gov.br/pncp/"),("Comercial Centro-Oeste","Comércio atacadista","Goiânia","GO","hiring","Assistente de contas a receber","Vaga demonstrativa para contas a receber e acompanhamento de títulos.","Exemplo fictício de evidência; não é lead real.","Demonstração","https://www.gov.br/receitafederal/")]
            for name,seg,city,uf,kind,title,desc,evidence,src,url in rows:
                c=Company(name=name,segment=seg,city=city,state=uf); db.add(c); db.flush(); score,reason=score_opportunity(kind,desc,evidence,url)
                db.add(Opportunity(company_id=c.id,kind=kind,title=title,description=desc,evidence=evidence,source_name=src,source_url=url,score=score,score_reason=reason,status="review",confidence=0.2,is_verified=False))
            db.commit()
    finally: db.close()
@app.on_event("startup")
def startup(): ensure_schema(); seed()
@app.get("/")
def dashboard(): return FileResponse(frontend/"index.html")
