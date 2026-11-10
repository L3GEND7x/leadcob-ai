#!/bin/sh
set -eu
umask 077
BACKUP_DIR=${BACKUP_DIR:-/backups}
temporary=''
trap 'if [ -n "$temporary" ]; then rm -f "$temporary"; fi' EXIT

backup_once() {
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  temporary=$(mktemp "$BACKUP_DIR/.leadcob-$stamp.XXXXXXXX") || return 1
  destination="$BACKUP_DIR/leadcob-$stamp-${temporary##*.}.dump"
  if pg_dump --format=custom --file="$temporary" && pg_restore --list "$temporary" >/dev/null; then
    mv "$temporary" "$destination" || return 1
    temporary=''
    # A retenção começa apenas depois de existir um novo backup válido.
    find "$BACKUP_DIR" -name 'leadcob-*.dump' -type f -mtime +13 -delete ||
      echo 'Falha ao limpar backups antigos; confira o espaço em disco.' >&2
    echo "$destination"
  else
    rm -f "$temporary"
    temporary=''
    echo 'Falha ao criar ou verificar backup' >&2
    return 1
  fi
}

if [ "${1:-}" = '--once' ]; then
  backup_once
  exit $?
fi
while true; do
  if backup_once; then
    sleep 86400
  else
    # Uma falha deve ser tentada novamente antes do próximo ciclo diário.
    sleep 3600
  fi
done
