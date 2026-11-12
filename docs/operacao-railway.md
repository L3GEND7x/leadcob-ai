# Operação online na Railway

Alternativa gerenciada à VPS para **um único proprietário**. A Railway fornece domínio HTTPS e PostgreSQL privado; o backup diário é um serviço cron separado que envia um dump criptografado para a Backblaze B2. Esta configuração **não foi implantada em uma conta real**. A conta Railway, cobrança e variáveis secretas são necessárias. Não compartilhe chaves pelo chat nem grave valores reais no GitHub.

## Aplicativo

1. Crie um projeto na Railway, adicione PostgreSQL e um serviço a partir deste repositório GitHub, branch `main`. Mantenha o Postgres sem acesso público.
2. No serviço do aplicativo, defina `RAILWAY_DOCKERFILE_PATH=infra/Dockerfile`. Em **Settings → Deploy**, configure **Pre-deploy Command** como `alembic -c /app/alembic.ini upgrade head` e **Healthcheck Path** como `/api/health`. Limite a uma réplica até existir coordenação explícita das migrações.
3. Em **Settings → Networking → Public Networking**, clique em **Generate Domain**. Copie o endereço HTTPS resultante.
4. Em **Variables**, defina `APP_ENV=production`, `DATABASE_URL=${{Postgres.DATABASE_URL}}` (troque `Postgres` se o serviço tiver outro nome), `PUBLIC_URL=https://<domínio-gerado>`, `ADMIN_USERNAME` e `ADMIN_PASSWORD_HASH`. Gere o hash com `PYTHONPATH=backend python -m app.core.security` em um ambiente local com as dependências instaladas; a senha original nunca entra nas variáveis do serviço. Defina `DEMO_SEED=false`. O backend aceita a URL PostgreSQL fornecida pela Railway e escolhe o driver psycopg instalado no projeto.
5. Revise e aplique as variáveis. Verifique o log do pre-deploy, o status saudável e o acesso HTTPS. O login deve rejeitar senha incorreta e liberar somente a conta configurada. Não importe dados financeiros reais antes do primeiro backup externo testado.

### Trocar a senha do administrador

Troque a senha se ela já apareceu em uma conversa, e-mail, print ou documento. O painel guarda **só o hash** (`ADMIN_PASSWORD_HASH`). A senha em si fica com você, de preferência num gerenciador de senhas.

1. **Faça primeiro o merge e o deploy da versão que encerra sessões na troca.** A partir dela, ao mudar `ADMIN_PASSWORD_HASH` (ou `ADMIN_USERNAME`), todas as sessões abertas com a senha anterior deixam de valer, mesmo depois de reiniciar. Sem isso, uma sessão aberta antes da troca continuaria válida por até 8 horas.
2. No **seu computador**, crie a nova senha no gerenciador de senhas: no mínimo 14 caracteres, nunca usada antes. Depois rode `python3 scripts/gerar_hash_senha.py`.
   - O script só precisa do Python 3. Você pode baixar só esse arquivo do GitHub.
   - Digite a senha duas vezes. Ela não aparece na tela e não é gravada.
   - Copie só a linha que começa com `pbkdf2_sha256.`.
3. Na Railway, abra o serviço do painel → **Variables** → `ADMIN_PASSWORD_HASH`. Substitua o valor pela nova linha, sem espaços nem quebra de linha, e aplique as mudanças.
4. Depois do deploy, confira três coisas:
   - a sessão antiga caiu;
   - a senha antiga é recusada;
   - a nova senha entra.

   Cinco tentativas erradas bloqueiam o login por 15 minutos.
5. Nunca envie a senha nem o hash por chat, issue ou PR. O hash não permite entrar, mas facilita tentar adivinhar a senha.

O serviço escuta a variável `PORT` da Railway. A assinatura ChatGPT não inclui a API: para usar o assistente, configure depois `OPENAI_API_KEY`, `OPENAI_MODEL`, orçamento e preços por token em variáveis seladas, seguindo `.env.example`.

### Carregar a base inicial de empresas na Railway

O job GitHub `importar-cnpj.yml` grava a base em `dados-cnpj` para a página publicada; ele **não** preenche o PostgreSQL do painel Railway. O importador `python -m app.jobs.import_railway_snapshot` carrega uma cópia fixa da base AM gerada em 10/11/2026 (23.348 registros), depois de conferir a revisão do banco. Ele insere somente empresas ausentes, preserva fichas e etapas do CRM existentes e ignora CNPJs na lista de supressão. Não importa e-mails, telefones, sócios nem dados de cobrança.

Após revisar e incorporar o PR que adiciona o importador:

1. Crie um serviço **temporário** no projeto Railway a partir da branch `main` do mesmo repositório, com `RAILWAY_DOCKERFILE_PATH=infra/Dockerfile`. Não adicione domínio público.
2. Defina somente `DATABASE_URL=${{Postgres.DATABASE_URL}}` e o comando de início `python -m app.jobs.import_railway_snapshot`. Não configure cron nem use o serviço web existente para esse job.
3. Inicie uma única execução e confira o log: deve mostrar a data do snapshot, a quantidade validada e os totais inseridos, existentes e suprimidos. O comando deve terminar sem erro. Em uma segunda execução, o total inserido deve ser zero.
4. Confira a quantidade de empresas no painel e remova o serviço temporário. O banco e o serviço web permanecem. Para outras UFs ou atualização periódica, prepare uma fonte e uma rotina próprias; este importador é deliberadamente limitado ao snapshot AM revisado.

O banco de produção deve ter o backup externo e o ensaio de restauração já validados antes da primeira importação. O arquivo é baixado de uma revisão fixa do ramo `dados-cnpj`; se o download falhar ou a estrutura divergir, o processo para antes de gravar qualquer linha.

## Backup externo diário

1. Use um bucket **privado** Backblaze B2 e uma chave de aplicativo padrão limitada a esse bucket, com leitura e gravação. Não use chave mestra nem chaves compartilhadas em conversas. Guarde também a senha Restic fora da Railway em um gerenciador de senhas.
2. Adicione um segundo serviço no mesmo projeto Railway, a partir do mesmo repositório, com `RAILWAY_DOCKERFILE_PATH=infra/Dockerfile.railway-backup`. Não gere domínio público para ele. Em **Settings → Cron Schedule**, configure `0 4 * * *` (04:00 UTC, 00:00 em Manaus). O processo termina após cada execução.
3. Nas variáveis desse serviço, referencie `PGHOST=${{Postgres.PGHOST}}`, `PGPORT=${{Postgres.PGPORT}}`, `PGUSER=${{Postgres.PGUSER}}`, `PGPASSWORD=${{Postgres.PGPASSWORD}}`, `PGDATABASE=${{Postgres.PGDATABASE}}`. Defina `RESTIC_REPOSITORY=s3:https://<endpoint-S3>/<nome-do-bucket>`, `RESTIC_PASSWORD` (senha nova e forte), `AWS_ACCESS_KEY_ID` (ID da chave B2 restrita) e `AWS_SECRET_ACCESS_KEY` (segredo dessa chave). Configure os valores sensíveis diretamente na Railway; não os copie para o chat ou repositório.
4. Dispare a primeira execução manualmente e verifique os logs: `pg_dump` e `pg_restore --list` devem passar antes do envio, seguido de `restic check`. Confirme que o snapshot existe. Configure alertas de falha do serviço agendado. O repositório Restic é inicializado uma única vez pelo script quando ainda não existe; falhas de autenticação não sobrescrevem um repositório existente.
5. Faça um ensaio de restauração em um banco isolado, como em **Ensaio de restauração** abaixo. Sem isso, a cópia não está validada para produção.

### Ensaio de restauração (banco isolado)

O ensaio usa a mesma imagem do backup no modo `BACKUP_MODE=restore-drill`. Ele:
- baixa o snapshot mais recente com a etiqueta `leadcob`;
- confere o dump;
- restaura com `pg_restore --no-owner --no-acl --exit-on-error` em um banco **vazio e separado**;
- lista as linhas de cada tabela e a versão do esquema.

O script **recusa** quando:
- falta `RESTORE_CONFIRM_ISOLATED=sim`;
- o destino é o mesmo servidor e banco de produção;
- o banco de destino já tem tabelas.

O ensaio nunca apaga nada.

1. No projeto Railway, adicione um **segundo PostgreSQL** e chame-o, por exemplo, de `Postgres-ensaio`. Mantenha-o sem acesso público. Ele começa vazio.
2. Adicione um serviço a partir do mesmo repositório, com `RAILWAY_DOCKERFILE_PATH=infra/Dockerfile.railway-backup`. Não gere domínio e não configure cron.
3. Variáveis desse serviço:
   - `BACKUP_MODE=restore-drill` e `RESTORE_CONFIRM_ISOLATED=sim`;
   - o banco de ensaio: `RESTORE_PGHOST=${{Postgres-ensaio.PGHOST}}`, `RESTORE_PGPORT=${{Postgres-ensaio.PGPORT}}`, `RESTORE_PGUSER=${{Postgres-ensaio.PGUSER}}`, `RESTORE_PGPASSWORD=${{Postgres-ensaio.PGPASSWORD}}` e `RESTORE_PGDATABASE=${{Postgres-ensaio.PGDATABASE}}`;
   - para a trava contra produção, **sem senha**: `PGHOST=${{Postgres.PGHOST}}`, `PGPORT=${{Postgres.PGPORT}}` e `PGDATABASE=${{Postgres.PGDATABASE}}`. O script compara e depois descarta essas três;
   - as mesmas `RESTIC_REPOSITORY`, `RESTIC_PASSWORD`, `AWS_ACCESS_KEY_ID` e `AWS_SECRET_ACCESS_KEY` do serviço `leadcob-backup`. Use referência, por exemplo `${{leadcob-backup.RESTIC_PASSWORD}}`, para não copiar valores.
4. Faça o deploy uma vez. O log deve terminar com `ENSAIO DE RESTAURAÇÃO CONCLUÍDO`.
5. Compare as contagens do log com o painel. Por exemplo, empresas em "Encontrar empresas" com `companies`, e interações e carteiras com `interactions` e `portfolios`. Considere as mudanças feitas depois do horário do snapshot.
6. Apague o serviço de ensaio e o `Postgres-ensaio`: eles têm cópia dos dados de produção. Registre data, ID do snapshot e contagens em `docs/ensaio-restauracao.md`.

### Se o backup falhar na autenticação

O script confere a configuração antes do dump e para com `ERRO de configuração: ...`. A mensagem traz o nome da variável, o tamanho e o tipo de problema. **Nunca traz o valor.**

| Mensagem no log | Causa | Como corrigir na Railway |
|---|---|---|
| `... contém quebra de linha` | O valor foi colado com Enter no fim (`\n` ou `\r`) ou com duas linhas | Apague o valor e cole de novo, em uma linha só |
| `AWS_ACCESS_KEY_ID deve ter só letras e números` | Rótulo (`keyID:`), aspas ou espaço junto do ID | Deixe só o **keyID** da chave de aplicativo |
| `... têm o mesmo valor` | ID e segredo trocados ou repetidos | `AWS_ACCESS_KEY_ID` = keyID; `AWS_SECRET_ACCESS_KEY` = applicationKey |
| `AWS_SESSION_TOKEN está definida` | Variável de outro provedor | Remova a variável |
| `invalid header field value for "Authorization"` (do Restic) | Quebra de linha no `AWS_ACCESS_KEY_ID` ou no `AWS_DEFAULT_REGION` (reproduzido em teste local) | Igual à primeira linha. A versão atual do script barra isso antes |
| `The Credential is malformed` (do servidor B2) | O servidor recusou o formato do ID ou do escopo. Pode ser texto extra, um ID de outra chave ou o nome da chave no lugar do keyID | Confira na Backblaze o keyID da chave restrita ao bucket |

`RESTIC_PASSWORD` é independente da chave B2. Não troque essa senha depois do primeiro backup: sem ela os snapshots não podem ser restaurados.

O backup remoto não apaga snapshots automaticamente. Planeje retenção e proteção contra exclusão com o provedor, depois de ensaiar a compatibilidade com Restic. Não ative retenção padrão/Object Lock às cegas: o Restic precisa gerenciar arquivos de bloqueio. Os backups nativos de volumes da Railway não substituem essa cópia externa, pois a restauração deles é limitada ao mesmo projeto e ambiente.
