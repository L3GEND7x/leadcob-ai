#!/bin/sh
set -eu
umask 077

for required in PGHOST PGUSER PGPASSWORD PGDATABASE RESTIC_REPOSITORY RESTIC_PASSWORD AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY; do
  eval "value=\${$required:-}"
  if [ -z "$value" ]; then
    echo "Configuração ausente: $required" >&2
    exit 1
  fi
done
case "$RESTIC_REPOSITORY" in
  s3:https://*) ;;
  *) echo 'Use um destino S3 com TLS.' >&2; exit 1 ;;
esac

temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
dump="$temporary/leadcob-$(date -u +%Y%m%dT%H%M%SZ).dump"
echo 'Gerando dump PostgreSQL.'
pg_dump --format=custom --file="$dump"
pg_restore --list "$dump" >/dev/null
echo 'Dump local verificado; consultando o repositório Restic.'

# Existing repositories are not overwritten. An invalid key or network failure
# will make init fail safely, and the scheduled job reports a failed run.
if ! timeout 60 restic cat config >/dev/null; then
  echo 'Repositório não encontrado ou inacessível; tentando inicialização.'
  timeout 60 restic init
fi
echo 'Enviando dump criptografado.'
restic backup "$dump" --tag leadcob
echo 'Conferindo o repositório remoto.'
restic check
echo 'Dump verificado e backup criptografado enviado ao armazenamento externo.'
