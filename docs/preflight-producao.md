# Preflight privado de produção

Executar após a migração Alembic, com a revisão aprovada, no serviço web
privado da Railway, em janela de implantação autorizada:

```sh
python -m app.jobs.production_readonly_preflight
```

Valida schema, usa transação PostgreSQL REPEATABLE READ READ ONLY e timeouts
locais. Não altera CRM, dados, contas ou contatos. Emite apenas contagens
agregadas, resultado, tempo e revisão. Testa inventário, qualificação,
contactabilidade, central, pesquisa, funil, configuração da IA, infraestrutura
e cenário financeiro sintético. Uma falha retorna código de saída não zero:
o pré-deploy deve impedir a liberação da nova versão até revisão.

Não chama o provedor de IA, não executa geração, não faz login nem valida
interfaces em produção. O relatório não certifica cobertura nacional.
Use o diagnóstico de IA e a homologação autenticada do proprietário
separadamente. Nunca exponha credenciais ou dados de clientes nos logs.
Não configure como job recorrente: executa somente durante uma implantação
aprovada. Não utilizar em banco de testes com dados de produção copiados.
