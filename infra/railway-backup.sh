#!/bin/sh
set -eu
umask 077

. "$(dirname "$0")/railway-backup-lib.sh"

for required in PGHOST PGUSER PGPASSWORD PGDATABASE; do
  eval "value=\${$required:-}"
  [ -n "$value" ] || fail "variável ausente ou vazia: $required"
done
check_restic_config

temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
dump="$temporary/leadcob-$(date -u +%Y%m%dT%H%M%SZ).dump"
echo 'Etapa 1/4: gerando dump PostgreSQL.'
pg_dump --format=custom --file="$dump"
pg_restore --list "$dump" >/dev/null
echo "Dump local verificado ($(wc -c < "$dump" | tr -d ' ') bytes)."

echo 'Etapa 2/4: consultando o repositório Restic.'
# Repositórios existentes não são sobrescritos: se a configuração já existir, "restic init"
# falha sem apagar nada e a execução agendada aparece como falha.
if ! timeout 60 restic cat config >/dev/null; then
  echo 'Repositório não encontrado ou inacessível; tentando inicialização.'
  timeout 60 restic init
fi
echo 'Etapa 3/4: enviando dump criptografado.'
restic backup "$dump" --tag leadcob
echo 'Etapa 4/4: conferindo o repositório remoto.'
restic check
echo 'Snapshot mais recente com a etiqueta leadcob:'
restic snapshots --tag leadcob --latest 1
echo 'BACKUP CONCLUÍDO: dump verificado, enviado ao armazenamento externo e repositório conferido.'
