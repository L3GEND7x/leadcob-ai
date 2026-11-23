#!/bin/sh
# Recovery drill against a temporary local PostgreSQL cluster, never production.
set -eu
umask 077

[ "$#" -eq 1 ] || { echo "Usage: verify-restore <local-archive.dump>" >&2; exit 1; }
dump=$1
[ -s "$dump" ] || { echo "Backup dump missing." >&2; exit 1; }
case "$dump" in *.dump) ;; *) echo "Backup must be a custom .dump file." >&2; exit 1;; esac

work=$(mktemp -d /tmp/leadcob-restore-XXXXXXXX)
started=no
cleanup() {
    if [ "$started" = yes ]; then
        su-exec postgres pg_ctl -D "$work/pg" -m immediate -w stop >/dev/null 2>&1 || true
    fi
    rm -rf "$work"
}
trap cleanup EXIT

# Prove the snapshot just uploaded can be downloaded from Restic intact.
echo "Etapa 5/6: baixando ultimo snapshot criptografado para conferencia."
restic restore latest --tag leadcob --target "$work/restored"
restored=$(find "$work/restored" -type f -name 'leadcob-*.dump' | sort | tail -n 1)
[ -n "$restored" ] && [ -s "$restored" ] || { echo "Restic snapshot without dump." >&2; exit 1; }
original_hash=$(sha256sum "$dump" | cut -d ' ' -f 1)
restored_hash=$(sha256sum "$restored" | cut -d ' ' -f 1)
[ "$original_hash" = "$restored_hash" ] || { echo "Restored snapshot digest mismatch." >&2; exit 1; }
pg_restore --list "$restored" >/dev/null

# Eliminate implicit production DB connectivity before invoking SQL tooling.
unset DATABASE_URL PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD PGSSLMODE PGHOSTADDR
mkdir -m 700 "$work/pg" "$work/socket"
chown -R postgres:postgres "$work"
export PGHOST="$work/socket" PGPORT=65432 PGUSER=postgres PGDATABASE=postgres
unset PGPASSWORD

echo "Etapa 6/6: ensaio de restore em PostgreSQL local isolado, sem rede TCP."
su-exec postgres initdb -D "$work/pg" -A trust --no-instructions >"$work/initdb.log" 2>&1 || {
    echo "Unable to initialize temporary database." >&2; exit 1;
}
su-exec postgres pg_ctl -D "$work/pg" -o "-c listen_addresses='' -c unix_socket_directories=$work/socket -c unix_socket_permissions=0700 -p $PGPORT" -w start >"$work/start.log" 2>&1 || {
    echo "Unable to start isolated PostgreSQL." >&2; exit 1;
}
started=yes
createdb -h "$PGHOST" -p "$PGPORT" -U postgres leadcob_restore
pg_restore --exit-on-error --no-owner --no-acl --host="$PGHOST" --port="$PGPORT" \
    --username=postgres --dbname=leadcob_restore "$restored"
tables=$(psql -X -tA -v ON_ERROR_STOP=1 -h "$PGHOST" -p "$PGPORT" -U postgres \
    -d leadcob_restore -c "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='public'")
[ "$tables" -gt 0 ] || { echo "Restore produced no public tables." >&2; exit 1; }
echo "RESTAURACAO_AUTOMATICA_OK: snapshot conferido; $tables tabelas restauradas no banco local temporario."
