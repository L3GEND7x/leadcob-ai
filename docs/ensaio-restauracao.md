# Registro de ensaios de restauração

Cada ensaio registra **onde** foi feito, **qual snapshot** foi usado e o **resultado**. O backup só passa a ser
considerado operacional depois de um ensaio bem-sucedido **com o bucket real** (Backblaze B2) e o banco da Railway.

| Data (UTC) | Onde | Snapshot | Resultado | Responsável |
|---|---|---|---|---|
| 2026-11-11 17:14 | **Local (simulação)** — ver abaixo | `8ac5502b` (emulador S3) | OK: 22 tabelas, contagens idênticas | Claude |
| 2026-11-11 19:08 | **Railway + bucket `leadcob-ai-backup`** — ver abaixo | `f8c7e7d1` | OK: 22 tabelas, esquema `2b3f641847d9`, banco ainda sem dados de negócio | proprietária (execução) e Claude (análise do log) |
| [PREENCHER] | Railway, com dados reais | [PREENCHER] | [PREENCHER] | proprietária |

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

## Ensaio real de 2026-11-11 (Railway + Backblaze B2)

**Backup (serviço `leadcob-backup`).**
- Primeira execução completa às 18:20 UTC (14:20 em Manaus). O bucket estava vazio, então o script criou o repositório Restic (`026c66f662`).
- Dump verificado de 60.061 bytes, enviado como o snapshot `a788ae04`, seguido de `restic check` e `BACKUP CONCLUÍDO`.
- Um segundo snapshot, `f8c7e7d1`, às 18:55 UTC, com o mesmo tamanho. A origem dessa execução está [NECESSÁRIO CONFERIR]: provavelmente uma execução manual.
- Antes disso, a conferência de credenciais (PR #32) barrou três configurações erradas, sem exibir valores:
  - ID e segredo com o mesmo valor;
  - segredo com quebra de linha (32 bytes).

**Ensaio (serviço temporário `leadcob-ensaio`, `BACKUP_MODE=restore-drill`, banco vazio `Postgres-ensaio`).**
1. Listou os 2 snapshots e restaurou o mais recente, `f8c7e7d1`, com o Restic conferindo o hash de cada bloco (58,653 KiB).
2. Dump recuperado: `leadcob-20261111T185541Z.dump`, 60.061 bytes, sha256 `59153f321d169860…`. O dump foi conferido com `pg_restore --list`.
3. `pg_restore --no-owner --no-acl --exit-on-error` terminou **sem erro**, com as ferramentas do PostgreSQL 18 da imagem.
4. Banco restaurado:
   - 22 tabelas, a mesma estrutura do ensaio local;
   - `alembic_version` = `2b3f641847d9`;
   - todas as tabelas com 0 linhas, exceto `alembic_version` 1, `login_attempts` 1 e `login_sessions` 2.

**Leitura.**
- *Fato:* o caminho completo (dump → B2 → Restic → restauração em banco isolado) funciona na Railway com PostgreSQL 18.
- *Fato:* o banco de produção ainda não tinha dados de negócio. Por exemplo, `companies` tinha 0 linhas.
- *Limite:* a integridade com volume real **não** foi testada. Repita o ensaio depois de importar dados reais e compare as contagens com o painel.

**Depois do ensaio:** apagar o serviço `leadcob-ensaio` e o banco `Postgres-ensaio`, porque eles guardam cópia dos dados de produção.
