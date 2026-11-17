# Auditoria financeira — PR 125

Evidência: execução Testes 223, https://github.com/L3GEND7x/leadcob-ai/actions/runs/44163380252, commit 53f9b733ddf115749758486f039c80a16c42cc16: 235 passed, 1 failed, 3 warnings. Falha em tests/test_alembic.py::test_initial_revision_and_upgrade_idempotence, etapa alembic check. Seis tabelas financeiras e índice de eventos existem nas migrações mas não no metadata. Correção: registrar os modelos com os mesmos tipos, restrições e índice, sem reescrever migrações ou suprimir o teste. Isso também permite criar tabelas no bootstrap local. Aguardar CI do novo commit para confirmar.

Teste de implantação online 122 aprovado naquele commit, não valida o fluxo financeiro completo.

## Pendências para lançamento
- PR 115 (cotas e vigência) não mesclado na consulta; PR 116 mesclado.
- Homologação Asaas real em sandbox, formato de eventos, limites no proxy, concorrência e falhas entre reserva e POST.
- Fluxo de conciliação ainda manual, sem worker, sem confirmação de saldo bancário, sem cobrança recorrente nem integração de produção.
- Revisar concorrência entre vínculo manual, emissão e cancelamento; provar isolamento por organização com testes de rotas e PostgreSQL.
- Renovação baseada em baixa manual e período contíguo em UTC; sandbox vinculado/reservado bloqueado. Não comprova depósito real.
- Nenhuma alteração de credenciais ou de produção autorizada neste PR.

Não considerar a auditoria encerrada até CI verde e validações integradas. Não desativar alembic check para obter aprovação.
