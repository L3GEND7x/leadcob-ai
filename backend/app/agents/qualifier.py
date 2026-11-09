from app.services.scoring import score_opportunity


class QualificationAgent:
    def run(self, opportunity):
        if opportunity.commercial_signal and opportunity.evidence_level:
            # Registros captados (editais, vagas) já chegam pontuados pelo classificador da fonte.
            proven = opportunity.commercial_signal == "oportunidade_comprovada"
            return {"score": opportunity.score, "reason": opportunity.score_reason,
                    "recommended_status": "qualified" if proven else "review"}
        score, reason = score_opportunity(opportunity.kind, opportunity.description, opportunity.evidence, opportunity.source_url)
        return {"score": score, "reason": reason, "recommended_status": "qualified" if score >= 55 else "review"}
