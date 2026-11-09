class AuditAgent:
    def run(self, opportunity, research, qualification):
        issues = []
        if not research["evidence_present"]: issues.append("Sem evidência textual.")
        if not research["url_present"]: issues.append("Sem URL de origem; validar manualmente.")
        if opportunity.kind == "outsourcing": issues.append("Terceirização é hipótese até confirmação direta da empresa.")
        if opportunity.kind == "public_procurement":
            if opportunity.evidence_level != "confirmada_api_oficial":
                issues.append("Registro só localizado no índice de busca; confirmar na API oficial ou no edital.")
            if opportunity.relevance == "revisar":
                issues.append(f"Aderência duvidosa: {opportunity.relevance_reason}")
            if opportunity.opportunity_class != "edital_aberto":
                issues.append("Não há prazo de propostas aberto: tratar como sinal de mercado, não como licitação disponível.")
            issues.append("Ler o edital: habilitação, qualificação técnica, forma de remuneração e prazo.")
        return {"passed": research["evidence_present"] and qualification["score"] >= 35, "issues": issues, "human_review_required": True}
