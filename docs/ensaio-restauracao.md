# Registro de ensaios de restauração

Cada ensaio registra **onde** foi feito, **qual snapshot** foi usado e o **resultado**. O backup só passa a ser
considerado operacional depois de um ensaio bem-sucedido **com o bucket real** (Backblaze B2) e o banco da Railway.

| Data (UTC) | Onde | Snapshot | Resultado | Responsável |
|---|---|---|---|---|
| 2026-11-11 17:14 | **Local (simulação)** — ver abaixo | `8ac5502b` (emulador S3) | OK: 22 tabelas, contagens idênticas | Claude |
| [PREENCHER] | Railway + bucket `leadcob-ai-backup` | [PREENCHER] | [PREENCHER] | proprietária |

## Ensaio local de 2026-11-11 (simulação, não substitui o ensaio real)

**O que foi usado:** os scripts `infra/railway-backup.sh` e `infra/railway-restore-drill.sh` deste ramo, **sem alteração**,
com restic 0.16.4 real, PostgreSQL 16.15 real e um emulador S3 local com TLS (moto) no lugar da Backblaze.
Banco de origem com o esquema criado pelo Alembic (`2b3f641847d9`) e dados **de teste** (25 empresas "EMPRESA DE TESTE NN LTDA").

**Diferenças em relação à produção:** PostgreSQL 16 (produção: 18.6); emulador S3 (produção: Backblaze B2);
credenciais falsas. Portanto **não testa** a chave B2, a rede da Railway nem o PostgreSQL 18.

**Resultado observado:**
1. Backup: configuração conferida → dump (61.259 bytes) verificado com `pg_restore --list` → `restic init` (repositório
   novo) → `restic backup` (snapshot `f799d904`) → `restic check` "no errors were found" → snapshot listado.
2. Segunda execução: não reinicializou o repositório; snapshot `8ac5502b`; `restic check` sem erros; 2 snapshots.
3. Travas do ensaio: recusou sem `RESTORE_CONFIRM_ISOLATED=sim`; recusou destino igual ao banco de produção; recusou
   banco de destino com tabela. Nos três casos nada foi restaurado e o banco de origem continuou com 25 empresas.
4. Ensaio: baixou o snapshot `8ac5502b`, dump íntegro, `pg_restore --exit-on-error` sem erro, 22 tabelas.
   Contagens **idênticas** entre origem e restaurado em todas as tabelas (ex.: `companies` 25, `interactions` 35,
   `audit_logs` 35, `alembic_version` 1) e o mesmo hash MD5 do conteúdo da tabela `companies` nos dois bancos.
5. O aplicativo abriu o banco restaurado: busca de empresas `200` com total 25; funil `200`.
