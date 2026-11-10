#!/bin/sh
set -eu
umask 077
while true; do
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  destination="/backups/leadcob-$stamp.dump"
  if pg_dump --format=custom --file="$destination" && pg_restore --list "$destination" >/dev/null; then
    find /backups -name 'leadcob-*.dump' -type f -mtime +13 -delete
  else
    rm -f "$destination"
    echo 'Falha ao criar ou verificar backup' >&2
  fi
  sleep 86400
done
