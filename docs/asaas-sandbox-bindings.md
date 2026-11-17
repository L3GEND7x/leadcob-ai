# Asaas sandbox — vínculos persistentes

Migração posterior aos recebíveis internos. Tabelas exclusivas do sandbox, com identificadores externos únicos e associação ao recebível e à organização. A verificação interna consulta somente vínculos já persistidos e recebíveis abertos; dados do provedor não são aceitos como prova isolada.

Nenhuma rota pública, baixa, assinatura, emissão, webhook ou configuração de produção foi ativada. Não há ainda fluxo administrativo para cadastrar os vínculos; a próxima etapa deve implementá-lo com autorização, auditoria e validação no provedor. Emissão exige reserva persistente e tratamento de resultado incerto antes de repetir POST. Webhooks exigem autenticação e reconsulta independente. Homologação com conta sandbox real continua pendente. Não utilizar resultado sandbox para liberar acesso real.

Teste unitário usa SQLite e MockTransport, não valida a migração contra PostgreSQL nem acessa o provedor real.
