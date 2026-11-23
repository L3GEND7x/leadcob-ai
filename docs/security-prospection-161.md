# Auditoria de segurança #161 — etapa parcial e verificável

## Evidência anterior
#160 mesclado na main, três workflows aprovados (44555687780, 44555687809, 44555687782). Último deploy Railway verificado ainda no merge #152 (75b0dda48053042a9b03689c54c58e4f5ad3c53a).

## Falhas observadas
1. GET /registry-search não aplicava cota por organização; requisições repetidas percorriam até 100 mil registros em memória e expunham endpoint a abuso.
2. Botão de importação usava POST /leads com nome/notas informados pelo navegador, sem verificar novamente elegibilidade cadastral e supressão global/local, nem impedir inclusão duplicada do mesmo CNPJ no CRM.
3. Excluir um lead importado sem apagar seu vínculo estruturado poderia causar bloqueio de reimportação e violação de chave estrangeira.

## Alterações
- POST /registry-search substitui GET. Mesmo fluxo de autenticação comercial, origem e CSRF, com bloqueio de organização e contador persistente de até 30 consultas por hora UTC por organização. Exige permissão de escrita; viewers não podem pesquisar nesta etapa. Sem comunicação externa automática.
- POST /registry-import aceita CNPJ e revalida dados da Receita, situação ativa, natureza empresarial, conflitos entre duplicatas, supressões do assinante e globais, e assinatura. Cria lead identificado e vínculo único (organização, CNPJ); dados privados do proprietário e contatos de outros assinantes não entram no novo lead. Rota passa pelo enforcement de cota de leads quando ligado.
- Exclusão de lead importado remove seu vínculo da mesma organização na mesma transação. Reimportação exige nova validação.
- Migração Alembic cria tabelas de quota e vínculo; teste sintético de isolamento, limites, bloqueios e importação escrito.

## Limites e pendências
A pesquisa usa cadastro público local parcialmente importado, não prova demanda ou disponibilidade de contatos. A mesma empresa ainda pode ser criada manualmente pelo endpoint de leads genéricos sem CNPJ estruturado; tal entrada não é uma importação validada da Receita. Credenciais e custos reais não foram acessados. O limite de 30 requisições por hora é política experimental, não SLA nem proteção integral contra DDoS. A validação de procedência depende de string de origem em dados legados, que não é atestado criptográfico. Não houve auditoria completa de dependências, testes adversariais HTTP, concorrência real multi-worker, controles de retenção/exclusão LGPD, termos de tratamento ou avaliação jurídica final. As configurações experimentais continuam desativadas por padrão.

## Antes de implantar
Exigir CI verde, avaliar impacto no GET anterior, backup PostgreSQL e migrações revisadas, testar CSRF e origem, isolamento entre organizações, concorrência PostgreSQL, supressões e exclusão do lead, medir latência e só então habilitar por decisão explícita. Railway não foi alterada nesta etapa.
