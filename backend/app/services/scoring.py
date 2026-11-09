def score_opportunity(kind, description, evidence, source_url):
    """Heurística inicial explicável; score não é probabilidade nem prova de compra."""
    text = f"{description} {evidence}".lower()
    score, why = 0, []
    if evidence.strip(): score += 25; why.append("evidência textual registrada +25")
    if source_url: score += 10; why.append("URL de origem informada +10")
    terms = ["cobrança", "inadimpl", "recuperação de crédito", "contas a receber", "negociação", "carteira vencida", "crédito", "financeiro"]
    found = [x for x in terms if x in text]
    if found:
        pts = min(30, 10 + 5*(len(found)-1)); score += pts; why.append(f"sinais: {', '.join(found)} +{pts}")
    pts = 10 if kind == "hiring" else 15
    score += pts; why.append(f"frente {kind} +{pts}")
    if any(x in text for x in ["urgente", "imediata", "grande volume", "alto volume"]): score += 10; why.append("sinal de urgência/volume +10")
    return min(score,100), "; ".join(why)
