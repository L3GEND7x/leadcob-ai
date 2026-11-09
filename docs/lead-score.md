# Lead score explicável (0–100)

Ordem de prioridade de trabalho comercial. **Não é probabilidade de contratação nem de inadimplência.**
Código: `backend/app/services/lead_score.py`. Cada componente declara a natureza da informação:
**fato** (fonte verificável), **indício** (sugere, não comprova) ou **hipótese** (premissa comercial).

| Componente | Pontos | Natureza | Regra |
|---|---|---|---|
| Aderência ao serviço | 0–22 | hipótese | Setores que costumam ter carteira a receber: 22. Setores com recebíveis menos típicos: 12. Órgão público: 12. Sem CNAE: 10. Representação comercial: 6. Concorrente (CNAE 8291): 0 |
| Evidência comercial | 0–30 | fato | Sinal mais forte + 3 por sinal adicional (teto 30). Edital aberto, aderente e confirmado na API oficial: 30; vaga para equipe própria de cobrança: 25; área de recuperação estruturada: 20; outras vagas de cobrança ou edital a revisar: 15; sinal manual com evidência: 15; contratação pública encerrada/direta ou vaga encerrada: 8; sinal manual sem evidência: 5 |
| Atualidade | 0–10 | fato | Sinal mais recente: até 30 dias 10; até 90 dias 6; até 180 dias 3 |
| Potencial de volume | 0–10 | indício | Porte "demais" 6, EPP 4, ME 2; capital ≥ R$ 1 mi +4, ≥ R$ 100 mil +2 |
| Compatibilidade geográfica | 0–10 | fato | UF nas UFs de atuação 10; nenhuma UF configurada 5; UF desconhecida 3; fora 0 |
| Canal institucional | 0–5 | fato | Site ou e-mail institucional cadastrado |
| Possibilidade de contratação | 0–10 | fato | Cadastro ativo na Receita (ou órgão público com contratação publicada) +5; edital aberto ou vaga ativa +5 |
| Histórico comercial | −20 a +10 | fato | Resposta, reunião ou proposta registrada +10; "Acompanhar futuramente" −5; "Perdido" −20 |

Faixas: **80–100** prioridade alta · **60–79** intermediária · **40–59** pesquisar melhor · **0–39** baixa.

Pontuação zerada, com faixa própria: concorrente; empresa na lista de supressão ou em "Não contatar";
cadastro BAIXADA, INAPTA, NULA ou SUSPENSA.

Os pesos são uma regra inicial, não calibrada com resultados reais. Calibrar depois de haver
histórico suficiente de contatos e contratos no CRM.
