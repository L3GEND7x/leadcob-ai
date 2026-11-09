from pydantic import BaseModel, Field
class OpportunityCreate(BaseModel):
    company_name: str = Field(min_length=2, max_length=220)
    cnpj: str|None = None
    segment: str|None = None
    city: str|None = None
    state: str|None = Field(default=None, max_length=2)
    website: str|None = None
    institutional_email: str|None = None
    kind: str = Field(pattern="^(hiring|outsourcing|public_procurement)$")
    title: str = Field(min_length=3, max_length=250)
    description: str = ""
    evidence: str = Field(min_length=3)
    source_name: str = "Cadastro manual"
    source_url: str|None = None
