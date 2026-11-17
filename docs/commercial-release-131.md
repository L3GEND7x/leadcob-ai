# Prontidão comercial — LeadCob AI

GET /api/owner/commercial/readiness: diagnóstico somente leitura, autenticado pelo proprietário. Não retorna segredos. Verifica ambiente, banco, origem HTTPS, flags, presença das tabelas e catálogo de preços ativos. Presença de tabelas não substitui verificação de revisão Alembic nem testes de integridade. A chave e token sandbox são sinalizados apenas por configuração, sem validação no provedor. release_ready permanece false até processo de aceite separado.

## Antes de disponibilizar a clientes
1. CI verde; validar implantação correspondente ao commit.
2. Backup e ensaio de restauração em ambiente isolado; aplicar migrações conforme procedimento e confirmar revisão.
3. Concorrência PostgreSQL, isolamento de organizações, permissões e testes E2E desktop/mobile.
4. Homologar Asaas sandbox e confirmar recuperação de emissões incertas; não confundir pagamento de teste com pagamento real.
5. Validar termos, privacidade, retenção, suporte e incidente; estabelecer política de cobrança e cancelamento.
6. Configurar integração de pagamento de produção separada e aprovada; atualmente não implementada. Baixa real manual depende de verificação independente pelo proprietário.
7. Validar assinaturas e catálogo; habilitar autenticação e cotas somente após aprovação operacional.
8. Registrar evidência de cada gate e responsável; iniciar piloto restrito antes de lançamento amplo.

## Contingência
Suspender novas operações comerciais pelo procedimento aprovado, preservar registros, não apagar reservas para repetir emissão, reconciliar valores e investigar antes de restaurar acesso. Não fazer downgrade destrutivo. Reverter código apenas após avaliar compatibilidade com a revisão do banco.

Nenhuma configuração, credencial ou preço foi alterado. CI #129 aprovado; CI backend #130 aprovado, implantação online #130 em andamento na consulta. Testes do #131 ainda não executados.
