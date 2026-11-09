# Roadmap

1. MVP: dashboard, API, banco, cadastro, score e agentes básicos.
2. Produção: autenticação individual, Alembic, HTTPS, backups, segredos, logs, monitoramento, testes e CI.
3. Fontes: importação CNPJ oficial, fontes autorizadas de vagas, PNCP e sites institucionais dentro dos termos aplicáveis.
4. Inteligência: LangGraph, classificação, enriquecimento, deduplicação, atualização temporal e calibração do score.
5. CRM: Kanban, tarefas, histórico, exportação, modelos de abordagem, opt-out e aprovação de campanhas.


## Situação em 09/11/2026 (v0.3.0)
Concluído: PNCP validado; vagas Greenhouse/Lever; CNPJ (consulta e base de empresas-alvo); catálogo de fontes.
Próximo: sinais de demanda verificáveis (ver "planejadas" em `docs/fontes.md`), agendamento dos jobs (PNCP diário, CNPJ mensal) fora da requisição web, autenticação.
