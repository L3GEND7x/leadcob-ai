# Fila de contatos institucionais

Acesso exclusivo do proprietário. Após backup e migração Alembic, criar lote pelo endpoint `POST /api/contacts/discovery-jobs` com `{"company_ids":[1,2]}` (até 1.000 IDs reais por requisição). Consultar `GET /api/contacts/discovery-jobs/{job_id}` e `/items?limit=100&offset=0`.

No ambiente backend, com o mesmo banco:

```sh
python -m app.jobs.discover_contacts --max-items 20
```

O comando termina após o limite de tentativas ou quando não há itens elegíveis. Reexecutar para continuar. Itens interrompidos ficam elegíveis após cinco minutos, até três tentativas. Itens falhos terminais exigem novo lote. Não agendar até validar capacidade e tempos de coleta. Executar inicialmente apenas um worker; deduplicação entre lotes e métricas exatas após falha entre a gravação de contatos e a finalização do item não são garantidas. A coleta respeita as regras do coletor existente e não confirma a titularidade dos canais.

Não há serviço Railway ou agendamento ativado por este PR. Não há envio de mensagens. A interface visual e teste de carga em escala real continuam pendentes.
