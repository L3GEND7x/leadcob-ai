# AGENTS.md — LeadCob AI

Instruções obrigatórias para agentes de desenvolvimento (Claude Code, Codex,
ChatGPT e outros). O repositório é a fonte de continuidade; não presumir
acesso à conversa de outro agente.

1. Leia COLABORACAO.md, README.md, docs/continuidade-ia-27-11-2026.md,
   docs/homologacao-27-11-2026.md e o código/testes relevantes antes de editar.
2. Confirme HEAD de main, PRs em aberto, CI, versão implantada e mudanças locais.
   A fotografia de continuidade tem data; não trate números antigos como atuais.
3. Trabalhe em branch própria (claude/, codex/ ou chatgpt/), sem push direto
   para main, sem merge sem decisão do proprietário. Não sobrescreva trabalho
   concorrente. Cada PR deve ter um objetivo, testes e evidências.
4. Execute cd backend && python -m compileall -q app && python -m pytest -q tests
   e workflows relevantes. Atualize CHANGELOG em alteração de comportamento.
   Informe testes não executados; não declare aprovação por suposição.
5. Prioridade de entrega: corrigir P0/P1, preservar funcionalidades e evitar
   novas dependências, custo, mudança de identidade visual ou ampliação de escopo.
6. Dados exclusivamente institucionais de PJ na prospecção. Preserve opt-out,
   origem, rastreabilidade, deduplicação, autorização e isolamento por organização.
   Não invente contatos, empresas, evidências ou oportunidades. Diferencie
   registro, prospect, sinal e lead qualificado. Não envie mensagens automáticas.
7. Nunca exponha chaves, senhas, tokens, dados de clientes ou arquivos privados.
   Não habilite cobrança real, acesso comercial, importação maciça ou serviços
   pagos sem autorização específica; não altere banco de produção para testar.
8. Ao concluir, registre arquivos, PR, commit, resultados de testes, evidências,
   riscos, pendências e próximos passos em documentação de continuidade.
   Deploy bem-sucedido, testes sintéticos e HTTP 200 não são homologação integral.
