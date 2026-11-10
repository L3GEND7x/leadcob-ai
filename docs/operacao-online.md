# Operação online (instalação individual)

Esta configuração é para **um único proprietário**. O login e o banco estão centralizados no servidor, de modo que as alterações ficam disponíveis no navegador de outros dispositivos após atualização. Não habilite outras contas sem isolamento completo por organização.

## Implantação em VPS com domínio próprio

1. Configure um domínio com DNS apontando à VPS. Permita portas 80 e 443. Instale Docker Compose.
2. Copie `.env.example` para `.env` e ajuste `DOMAIN`, `POSTGRES_PASSWORD` com senha forte, `ADMIN_USERNAME` e `ADMIN_PASSWORD_HASH`. O Compose define `APP_ENV`, `PUBLIC_URL` e a conexão com PostgreSQL; a senha admite caracteres especiais sem codificação manual de URL.
3. Gere o hash interativamente com `PYTHONPATH=backend python -m app.core.security` em um ambiente Python com `backend/requirements.txt` instalado. Cole apenas o hash em `.env`. Defina permissões restritas em `.env`.
4. Opcionalmente configure `OPENAI_API_KEY`, `OPENAI_MODEL`, orçamento mensal em USD e preços vigentes por milhão de tokens de entrada/saída. O assistente ficará desativado até configurar todos. Consulte a precificação oficial antes de preencher. A assinatura ChatGPT não fornece automaticamente uma chave de API.
   Para importar arquivos da Receita ou consultar o DataJud, configure também `RFB_SHARE_TOKEN` e `DATAJUD_API_KEY` com os valores públicos atuais obtidos nas páginas oficiais. Eles não são distribuídos no código.
5. Execute `mkdir -p backups && chmod 700 backups && docker compose -f docker-compose.cloud.yml up -d --build --wait`. O serviço `migrate` aplica a versão do banco antes do painel e do primeiro backup. O Caddy emite TLS automaticamente para o domínio. Visite `https://seu-dominio`.

`docker compose -f docker-compose.cloud.yml logs -f app proxy backup` acompanha erros. Nunca compartilhe `.env`, backups ou dados de clientes em repositório público. A VPS, o domínio e a chave OpenAI exigem contas e custos próprios. Esta configuração não foi implantada neste ambiente.

## Backup e restauração

O serviço `backup` faz dump customizado diário no diretório `./backups`, verifica o índice via `pg_restore --list`, publica o arquivo de forma atômica e mantém 14 dias. Em caso de falha, tenta novamente em uma hora. Um arquivo temporário `.leadcob-*` não é um backup válido. Para gerar um dump pontual, use `docker compose -f docker-compose.cloud.yml run --rm --no-deps backup --once`.

### Cópia externa criptografada (opcional)

O serviço `offsite` usa Restic para copiar os dumps locais a um bucket privado S3 compatível com HTTPS, criptografados antes do envio. Primeiro escolha e contrate o armazenamento, crie o bucket e credenciais com acesso restrito a ele. Preencha `RESTIC_REPOSITORY` (por exemplo `s3:https://s3.exemplo.com/bucket/leadcob`), `RESTIC_PASSWORD`, `AWS_ACCESS_KEY_ID` e `AWS_SECRET_ACCESS_KEY` no `.env` da VPS. A senha Restic é indispensável para recuperar os dados: guarde uma cópia **fora da VPS** em local seguro. Não reutilize o bucket para outros projetos.

Inicialize uma única vez com `docker compose -f docker-compose.cloud.yml --profile offsite run --rm --no-deps --entrypoint restic offsite init`. Depois inicie com `docker compose -f docker-compose.cloud.yml --profile offsite up -d offsite`. Para ensaiar imediatamente, use `docker compose -f docker-compose.cloud.yml --profile offsite run --rm --no-deps offsite --once` após gerar um dump local. O envio periódico tenta novamente após uma hora se falhar, recusa dumps com mais de 30 horas e verifica a estrutura do repositório após o backup. Acompanhe `docker compose -f docker-compose.cloud.yml --profile offsite logs offsite`; monitore falhas e espaço do bucket. O serviço é opcional e não inicia sem `--profile offsite`.

Configure retenção e proteção contra exclusão no provedor (versionamento ou Object Lock, quando disponível) e teste a restauração externa periodicamente. Esta integração **não está ativa** até você fornecer armazenamento e credenciais; `restic check` não substitui a restauração de teste nem lê todo o conteúdo dos dumps. Backups no mesmo host não protegem contra perda da VPS.

Para recuperar uma cópia externa, numa máquina isolada com as mesmas credenciais e senha, execute `restic snapshots` e `restic restore latest --target /caminho/seguro`; selecione o dump recuperado e siga o procedimento de restauração abaixo. Não restaure diretamente sobre a produção sem ensaio.

Para ensaiar a restauração, crie um banco **separado**, sem dados de produção, e execute `pg_restore --no-owner --no-acl --exit-on-error -d leadcob_restore <arquivo.dump>` com as credenciais desse banco. Inicie uma instância de teste apontando para esse banco e confira empresas, tarefas, contatos, carteiras, valores e histórico antes de considerar a restauração validada. O workflow `cloud-smoke.yml` faz essa restauração em um PostgreSQL temporário a cada PR. Em produção, interrompa gravações, guarde um backup adicional e só então restaure no banco de destino.

A migração de SQLite antigo para PostgreSQL demanda rotina própria e conferência de contagens e valores. Preserve o banco antigo até concluir essa verificação. SQLite local continua recebendo tabelas e colunas legadas no startup. O PostgreSQL de produção usa exclusivamente migrações versionadas: `docker compose -f docker-compose.cloud.yml run --rm migrate` executa `alembic upgrade head`. Faça backup verificável antes de atualizar um banco existente. Um banco PostgreSQL já criado pelo aplicativo antigo, sem `alembic_version`, não deve receber `stamp head` às cegas: confira tabelas, colunas, índices e dados contra a revisão inicial e planeje a reconciliação antes de marcar sua versão. Falhas de migração impedem o painel de iniciar; o rollback da revisão inicial é bloqueado para evitar apagar dados.
