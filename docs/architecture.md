# Arquitetura

Fluxo alvo: fontes oficiais/autorizadas → adaptadores/coletores → Research Agent → Classifier → Company Enrichment → Qualification/Scoring → Audit Agent → Supervisor → CRM.

Implementado no MVP: API FastAPI, SQLAlchemy, PostgreSQL (SQLite fallback), dashboard responsivo, cadastro/listagem, score por regras, Supervisor, Research, Qualification e Audit. Classifier/Enrichment são esqueletos. Não há pesquisa web autônoma nesta entrega.

Agentes previstos:
- Supervisor: controla estados, retries e trilha de execução.
- Research: captura URL, data, trecho e origem.
- Classifier: separa vaga de cobrança e sinal de terceirização; deve descartar ou revisar sinais ambíguos.
- Enrichment: relaciona empresa, CNPJ, segmento e localização usando fontes autorizadas.
- Qualification: pontua aderência e força da evidência.
- Auditor: verifica proveniência, atualidade, inferências e riscos.

LangGraph pode ser introduzido na fase seguinte para persistência de estado, retries e human-in-the-loop. Redis está reservado no compose para workers futuros.


## Primeiro conector ativo: PNCP
Descoberta pelo índice de busca do portal → classificação de aderência → confirmação na API oficial de consulta →
gravação como `public_procurement` com evidência, prazo, valor, modalidade e nível de evidência. Detalhes, resultados
da validação real e limites em `docs/pncp-connector.md`.
