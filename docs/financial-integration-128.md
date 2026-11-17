# Testes integrados financeiros

Testes HTTP em SQLite isolado por caso: autenticação real do proprietário, CSRF, rejeição de organização incorreta, renovação idempotente e trilha de auditoria, reserva persistente após timeout, bloqueio de renovação sandbox e duas requisições concorrentes de criação do mesmo recebível. O timeout Asaas é simulado explicitamente e nenhuma chamada externa é efetuada. Não altera a aplicação ou configurações de produção.

CI do #127 aprovado (Testes 229 e implantação online 125). CI do #128 pendente. Concorrência em PostgreSQL, corrida entre vínculo manual e emissão, falhas entre reserva e POST, webhook real e homologação do provedor continuam pendentes. Aprovação do teste SQLite não comprova comportamento PostgreSQL. Não lançar comercialmente com essas pendências.
