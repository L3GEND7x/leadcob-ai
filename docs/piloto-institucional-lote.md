# Piloto institucional — importação pelo navegador

O proprietário autorizou PRs para validação no Actions, mantendo CI verde antes de merge e deploy. A produção #213 está ativa. #214, que corrige robots.txt em redirecionamentos, está verde (395 testes backend, 7 PostgreSQL, 4 workflows), mas ainda aberto em 26/11/2026. Integrar #214 antes de iniciar coleta externa do piloto.

## Novo fluxo
1. Abrir /owner/discovery na sessão do proprietário.
2. Selecionar JSON de 1 a 5 registros com os campos cnpj, website, source_url e evidence (apenas fontes públicas de PJ). A seleção e a prévia não escrevem dados.
3. A conciliação exata rejeita CNPJ ausente, duplicado, inválido, suprimido, concorrente, site conflitante, cadastro inconsistente e fila já pendente. Revisar titularidade e finalidade de cada registro elegível.
4. Confirmar os selecionados. Sites, auditoria e fila são registrados na mesma transação. Nenhuma busca externa, mensagem ou criação de empresa é executada por esta ação.
5. Selecionar o lote e processar uma empresa por acionamento; revisar contatos a verificar. Medir canais e fontes antes/depois.

Amostra de cinco sites pesquisados externamente em Manaus disponibilizada ao proprietário fora do repositório. Não presumir existência na base nem demanda por cobrança. Não inserir contatos automaticamente ou criar cadastro inexistente. A autenticação e a confirmação são do proprietário. Sem API paga, nova infraestrutura ou carga nacional. CI e piloto real não comprovados por esta alteração. Testes novos verificam prévia, confirmação, supressão, atomicidade, limite/deduplicação e existência do controle no navegador.