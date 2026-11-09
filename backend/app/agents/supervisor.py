from app.agents.researcher import ResearchAgent
from app.agents.qualifier import QualificationAgent
from app.agents.auditor import AuditAgent
class SupervisorAgent:
    def __init__(self): self.research=ResearchAgent(); self.qualifier=QualificationAgent(); self.auditor=AuditAgent()
    def run(self, opportunity):
        r=self.research.run(opportunity); q=self.qualifier.run(opportunity); a=self.auditor.run(opportunity,r,q)
        return {"research":r,"qualification":q,"audit":a}
