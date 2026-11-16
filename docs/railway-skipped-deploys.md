# Diagnóstico de deploys ignorados na Railway — 16/11/2026

## Escopo

Investigação do serviço `leadcob-web` no projeto Railway `leadcob-ai`, motivada por relatos anteriores de deploys
com estado `Skipped`.

## O que foi verificado

Configuração atual do serviço:
- fonte: repositório `L3GEND7x/leadcob-ai`;
- build: Dockerfile `infra/Dockerfile`;
- pre-deploy: `alembic -c /app/alembic.ini upgrade head`;
- healthcheck: `/api/health`;
- branch observada nos deploys: `main`;
- nenhuma configuração de **watch paths** apareceu no estado atual retornado pela Railway;
- nenhum deployment com status **SKIPPED** foi localizado no histórico recente consultável do serviço.

Deploys recentes visíveis estavam em estados `SUCCESS` ou `REMOVED` (deploys antigos substituídos).

## Leitura

**Fato:** não há evidência, na configuração atual, de que `watch paths` esteja causando deploys ignorados.

**Fato:** a Railway documenta que `Wait for CI` pode fazer um deploy ser ignorado quando os workflows não terminam
dentro do limite da plataforma.

**Fato:** a Railway também usa o termo “skipped build” quando reaproveita uma imagem já construída para o mesmo
código-fonte; isso é diferente de um deployment com status `SKIPPED`.

**Não confirmado:** a causa histórica dos deploys relatados como `Skipped`. O evento específico não está mais
presente no histórico recente disponível, portanto não é correto atribuir a causa a `Wait for CI` ou `watch paths`
sem o deployment original.

## Ação

A configuração atual não deve ser alterada apenas para “corrigir” um problema que não foi reproduzido. Se um novo
deployment aparecer como `SKIPPED`, registrar imediatamente:
1. ID do deployment;
2. horário;
3. commit;
4. status dos workflows GitHub naquele commit;
5. configuração de Source naquele momento.

Com esses dados, a causa pode ser fechada sem hipótese.
