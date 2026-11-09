class ResearchAgent:
    def run(self, opportunity):
        return {"source_present": bool(opportunity.source_name), "url_present": bool(opportunity.source_url),
                "evidence_present": bool(opportunity.evidence.strip()),
                "note": "Proveniência registrada pelo coletor (PNCP) ou pelo cadastro manual; demais fontes ainda não conectadas."}
