# Transferência da base nacional para PostgreSQL

Depende do staging nacional (PR #187). Um escopo por execução: competência,
UF e partição. O SQLite de origem é aberto somente para leitura, em snapshot
consistente. Os vinte arquivos devem estar confirmados e a junção sem
identidades pendentes. As tabelas Municipios, Cnaes e Naturezas da mesma
competência são lidas da configuração do staging; mantenha arquivos imutáveis.

## Preview
```sh
cd backend
python -m app.jobs.national_registry_transfer --stage /volume/privado/stage.sqlite --release AAAA-MM --uf AM --part 0
```
Substitua AAAA-MM pela competência validada. O preview percorre todas as páginas
e valida a contagem, sem acessar o banco da aplicação. Saída somente agregada.
Paginação por chave CNPJ em lotes de até 500; não carrega a UF em memória.

## Apply
Somente após preview aprovado, benchmark, orçamento, backup restaurado, revisão
Alembic correta, auditoria de CNPJs legados e janela de escritor único,
acrescente --apply --confirm-backup-and-exclusive-writer. Exige PostgreSQL.
A flag registra confirmação operacional do operador, não verifica backup
ou exclusividade automaticamente. Suspender cadastros e importadores
concorrentes: ainda não existe unicidade global de CNPJ.
Insere apenas ausentes, respeitando supressões e mantendo CRM/contatos.
Não atualiza cadastro existente, não importa sócios ou canais pessoais.
A transação é por lote, não por UF inteira: falha pode deixar lotes anteriores
confirmados. Reexecutar o escopo desde o início é idempotente sob escritor
único e CNPJ canônico; os registros já gravados são contados como existentes.
Não há cursor persistente, nem histórico de inserções após falhas parciais.
Não se pode declarar cobertura nacional a partir de uma transferência isolada.

O próximo passo é atualizar cadastros já existentes com proveniência,
competência, revisão de inconsistências e preservação de dados comerciais.
Nenhuma carga real ou contratação de infraestrutura foi executada neste PR.
