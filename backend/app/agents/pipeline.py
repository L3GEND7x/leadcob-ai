from app.agents.supervisor import SupervisorAgent
from app.db.models import AuditLog
def run_pipeline(db, opportunity):
    result=SupervisorAgent().run(opportunity)
    opportunity.score=result["qualification"]["score"]
    opportunity.score_reason=result["qualification"]["reason"]
    opportunity.status=result["qualification"]["recommended_status"]
    db.add(AuditLog(event="agent_pipeline_completed", entity_type="opportunity", entity_id=opportunity.id, details=result))
    db.commit(); db.refresh(opportunity)
    return result
