#!/bin/sh
set -eu
umask 077
BACKUP_DIR=${BACKUP_DIR:-/backups}

offsite_once() {
  for required in RESTIC_REPOSITORY RESTIC_PASSWORD AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY; do
    eval "value=\${$required:-}"
    if [ -z "$value" ]; then
      echo "Configuração ausente: $required" >&2
      return 1
    fi
  done
  case "$RESTIC_REPOSITORY" in
    s3:https://*|s3:s3.*) ;;
    *) echo 'Use um destino S3 com TLS.' >&2; return 1 ;;
  esac
  # Não arquivar um dump antigo se o pg_dump diário parou de funcionar.
  if ! find "$BACKUP_DIR" -maxdepth 1 -type f -name 'leadcob-*.dump' -mmin -1800 | grep -q .; then
    echo 'Nenhum dump local recente (até 30 horas); envio remoto cancelado.' >&2
    return 1
  fi
  restic backup "$BACKUP_DIR" --exclude "$BACKUP_DIR/.leadcob-*" --tag leadcob
  restic check
  echo 'Backup criptografado enviado e repositório remoto verificado.'
}

if [ "${1:-}" = '--once' ]; then
  offsite_once
  exit $?
fi
while true; do
  if offsite_once; then
    sleep 86400
  else
    sleep 3600
  fi
done
