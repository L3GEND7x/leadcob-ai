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

## Backup externo diário

1. Use um bucket **privado** Backblaze B2 e uma chave de aplicativo padrão limitada a esse bucket, com leitura e gravação. Não use chave mestra nem chaves compartilhadas em conversas. Guarde também a senha Restic fora da Railway em um gerenciador de senhas.
2. Adicione um segundo serviço no mesmo projeto Railway, a partir do mesmo repositório, com `RAILWAY_DOCKERFILE_PATH=infra/Dockerfile.railway-backup`. Não gere domínio público para ele. Em **Settings → Cron Schedule**, configure `0 4 * * *` (04:00 UTC, 00:00 em Manaus). O processo termina após cada execução.
3. Nas variáveis desse serviço, referencie `PGHOST=${{Postgres.PGHOST}}`, `PGPORT=${{Postgres.PGPORT}}`, `PGUSER=${{Postgres.PGUSER}}`, `PGPASSWORD=${{Postgres.PGPASSWORD}}`, `PGDATABASE=${{Postgres.PGDATABASE}}`. Defina `RESTIC_REPOSITORY=s3:https://<endpoint-S3>/<nome-do-bucket>`, `RESTIC_PASSWORD` (senha nova e forte), `AWS_ACCESS_KEY_ID` (ID da chave B2 restrita) e `AWS_SECRET_ACCESS_KEY` (segredo dessa chave). Configure os valores sensíveis diretamente na Railway; não os copie para o chat ou repositório.
4. Dispare a primeira execução manualmente e verifique os logs: `pg_dump` e `pg_restore --list` devem passar antes do envio, seguido de `restic check`. Confirme que o snapshot existe. Configure alertas de falha do serviço agendado. O repositório Restic é inicializado uma única vez pelo script quando ainda não existe; falhas de autenticação não sobrescrevem um repositório existente.
5. Faça um ensaio de restauração em ambiente separado: recupere um dump com `restic restore` e execute `pg_restore --no-owner --no-acl --exit-on-error` em um banco isolado. Confira contagens, carteiras e histórico. Sem isso, a cópia não está validada para produção.

O backup remoto não apaga snapshots automaticamente. Planeje retenção e proteção contra exclusão com o provedor, depois de ensaiar a compatibilidade com Restic. Não ative retenção padrão/Object Lock às cegas: o Restic precisa gerenciar arquivos de bloqueio. Os backups nativos de volumes da Railway não substituem essa cópia externa, pois a restauração deles é limitada ao mesmo projeto e ambiente.
