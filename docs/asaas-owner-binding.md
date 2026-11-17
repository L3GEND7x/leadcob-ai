# Cadastro administrativo de vínculos Asaas sandbox

Somente proprietário autenticado. Escrita exige origem e CSRF válidos. A rota GET /api/owner/commercial/organizations/{organization_id}/invoices/{invoice_id}/asaas-sandbox informa a referência externa determinística, se há vínculo e se o pagamento sandbox foi verificado. A rota PUT no mesmo endereço recebe customer_id e payment_id de uma cobrança já existente no sandbox.

A cobrança deve conter a referência exata retornada pelo GET, pertencer ao cliente informado, ter valor bruto igual ao recebível aberto e ser Pix ou boleto. O vínculo não pode ser substituído silenciosamente. A unicidade no banco protege contra reutilização dos identificadores e a criação gera evento de auditoria. A seleção inicial da conta de cliente é responsabilidade do proprietário; esta etapa não valida a titularidade legal do cliente.

Não há POST de cobrança no provedor, webhook, baixa automática, renovação ou liberação de acesso. Não incluir a chave sandbox no código ou logs. A verificação GET não comprova dinheiro real. Testes unitários adicionados; execução de CI, testes de integração de rotas, concorrência e homologação real ainda necessários. A próxima etapa deve persistir uma reserva de emissão antes de qualquer POST e bloquear repetição após resultado incerto.
