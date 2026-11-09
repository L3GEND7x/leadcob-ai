class OpportunityClassifier:
    def classify(self, text):
        t = text.lower()
        if any(x in t for x in ["vaga", "contrata", "analista de cobrança", "assistente de cobrança"]): return {"kind":"hiring", "confidence":0.7}
        if any(x in t for x in ["terceirização", "prestador de cobrança", "recuperação terceirizada"]): return {"kind":"outsourcing", "confidence":0.6}
        return {"kind":"review", "confidence":0.2}
