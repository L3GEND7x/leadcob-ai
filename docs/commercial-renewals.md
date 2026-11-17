# Renovação comercial controlada

Ação administrativa explícita, com autenticação e CSRF. Renova somente assinatura existente, não cancelada, com plano ativo e recebível do mesmo plano e organização, baixado manualmente. O período do recebível deve começar exatamente no fim da vigência existente (meia-noite UTC), sem lacuna e com fim futuro. Assinaturas com outros horários necessitam revisão administrativa, sem arredondamento silencioso.

Recebíveis com vínculo ou reserva Asaas sandbox são bloqueados para renovação, inclusive se baixados manualmente. O sistema não verifica extrato bancário: o proprietário continua responsável por confirmar o pagamento real antes da baixa. A renovação consome o recebível uma única vez por chave primária, com registro histórico e auditoria na mesma transação. Não modifica preços, não emite cobranças, não reativa organização suspensa, não cria assinaturas e não libera pagamento sandbox. Não há job recorrente nem bloqueio automático de acesso nesta etapa.

Testes unitários escritos, não executados. Validar integração, concorrência, migração e fluxo de baixa manual antes de uso comercial. As tabelas sandbox dependem das migrações Alembic anteriores.
