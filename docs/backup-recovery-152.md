# Backup e recuperação #152

#151 mesclado e três workflows aprovados. Ensaio lógico automatizado em PostgreSQL local descartável, com dois bancos aleatórios criados pelo script, dados exclusivamente sintéticos, pg_dump custom e pg_restore em transação. Compara tabelas, contagens e somas financeiras exatas, verifica propriedade de leads entre dois tenants e continuidade de sequência. Registra SHA-256, tamanho e duração. Remove bancos e arquivo temporário; publica somente relatório JSON. Nunca usa DATABASE_URL para selecionar o destino. Requer instância local dedicada leadcob_test e usuário leadcob_test. Não executado nesta revisão; CI pendente.

## Procedimento operacional proposto (não executado)
- Definir responsável, RPO/RTO e política de retenção; como ponto inicial sujeito a aprovação: backup diário, retenção de 30 dias e cópia semanal segregada.
- Usar mecanismo de backup do provedor PostgreSQL ou exportação lógica autenticada, com cliente compatível e armazenamento criptografado, acessos mínimos e cópia fora da instância. Nunca publicar dump, credenciais ou dados de clientes no GitHub Actions.
- Antes de migrações, verificar backup recuperável e revisão Alembic. Restaurar somente em ambiente de teste isolado, bloquear envio externo e integrações, conferir versão, tabelas, contagens, somas, chaves, permissões, índices, vínculos transacionais e sequências; invalidar sessões restauradas antes de qualquer acesso.
- Registrar horários de início/fim, perda de dados observada, diferenças e aceite; só promover destino de recuperação após aprovação e plano de reversão.

Limites: fixture usa Base.metadata.create_all, não comprova restauração da cadeia Alembic nem conformidade de esquema real, recuperação point-in-time, criptografia em repouso, recuperação de arquivos externos, política de retenção efetiva ou restauração de produção. Teste não verifica todos os valores individuais nem todas as chaves/índices. Backup produtivo, agendamento, monitoramento e metas RPO/RTO precisam de infraestrutura e aceite autorizado. Não houve acesso ao banco real.
