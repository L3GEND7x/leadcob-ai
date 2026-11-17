# Webhook Asaas sandbox

Endpoint POST /api/webhooks/asaas/sandbox. Configure apenas na conta sandbox, com HTTPS e variável secreta ASAAS_SANDBOX_WEBHOOK_TOKEN de pelo menos 32 caracteres aleatórios, igual ao token configurado no provedor. Header asaas-access-token. Não reutilizar a chave de API nem token de produção. Sem configuração, rejeita todas as solicitações. Referência: https://docs.asaas.com/docs/webhooks

O middleware libera somente o POST exato para autenticação própria. Limite de 64 KiB; aplicar também limite de tráfego no proxy. Persiste somente identificadores e horário local de recepção, não o payload completo. Responde sucesso depois do commit; duplicatas exatas não geram novo registro, colisões inconsistentes retornam 409. Eventos de pagamentos sem vínculo também são guardados, para futura investigação. Nenhum evento altera recebível, assinatura, saldo ou acesso. A próxima etapa deve reconsultar a API por identificador vinculado, processar o inbox de modo auditável e tratar estornos sem confiar na ordem ou no valor do evento.

Testes unitários escritos, ainda não executados. Validar migração, rota/middleware, concorrência, limites e formato real dos identificadores com o sandbox antes de configurar o provedor. Não configurar em produção.
