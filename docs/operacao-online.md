# Operação online (instalação individual)

Esta configuração é para **um único proprietário**. O login e o banco estão centralizados no servidor, de modo que as alterações ficam disponíveis no navegador de outros dispositivos após atualização. Não habilite outras contas sem isolamento completo por organização.

## Implantação em VPS com domínio próprio

1. Configure um domínio com DNS apontando à VPS. Permita portas 80 e 443. Instale Docker Compose.
2. Copie `.env.example` para `.env` e ajuste `DOMAIN`, `POSTGRES_PASSWORD` com senha forte, `ADMIN_USERNAME` e `ADMIN_PASSWORD_HASH`. O Compose define `APP_ENV`, `PUBLIC_URL` e a conexão com PostgreSQL; a senha admite caracteres especiais sem codificação manual de URL.
3. Gere o hash interativamente com `PYTHONPATH=backend python -m app.core.security` em um ambiente Python com `backend/requirements.txt` instalado. Cole apenas o hash em `.env`. Defina permissões restritas em `.env`.
4. Opcionalmente configure `OPENAI_API_KEY`, `OPENAI_MODEL`, orçamento mensal em USD e preços vigentes por milhão de tokens de entrada/saída. O assistente ficará desativado até configurar todos. Consulte a precificação oficial antes de preencher. A assinatura ChatGPT não fornece automaticamente uma chave de API.
   Para importar arquivos da Receita ou consultar o DataJud, configure também `RFB_SHARE_TOKEN` e `DATAJUD_API_KEY` com os valores públicos atuais obtidos nas páginas oficiais. Eles não são distribuídos no código.
5. Execute `mkdir -p backups && chmod 700 backups && docker compose -f docker-compose.cloud.yml up -d --build`. O Caddy emite TLS automaticamente para o domínio. Visite `https://seu-dominio`.

`docker compose -f docker-compose.cloud.yml logs -f app proxy backup` acompanha erros. Nunca compartilhe `.env`, backups ou dados de clientes em repositório público. A VPS, o domínio e a chave OpenAI exigem contas e custos próprios. Esta configuração não foi implantada neste ambiente.

## Backup e restauração

O serviço `backup` faz dump customizado diário no diretório `./backups`, verifica o índice via `pg_restore --list` e mantém 14 dias. Envie cópias criptografadas para **outro servidor ou serviço de armazenamento**, com política de retenção. Backups no mesmo host não protegem contra perda do host.

Para ensaiar a restauração, crie um banco **separado**, sem dados de produção, e execute `pg_restore --clean --if-exists --no-owner -d leadcob_restore <arquivo.dump>` com as credenciais desse banco. Inicie uma instância de teste apontando para esse banco e confira empresas, tarefas, contatos, carteiras, valores e histórico antes de considerar a restauração validada. Em produção, interrompa gravações, guarde um backup adicional e só então restaure no banco de destino.

A migração de SQLite antigo para PostgreSQL demanda rotina própria e conferência de contagens e valores. Preserve o banco antigo até concluir essa verificação. A geração de tabelas novas e colunas legadas continua ocorrendo no startup, e migrações versionadas ainda precisam ser implantadas antes de evolução estrutural contínua em produção.
