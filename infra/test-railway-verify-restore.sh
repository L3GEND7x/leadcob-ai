#!/bin/sh
set -eu
umask 077
work=$(mktemp -d /tmp/leadcob-restore-ci-XXXXXXXX)
chown postgres:postgres "$work"
mkdir "$work/sock"
chown postgres:postgres "$work/sock"
running=no
cleanup() {
    if [ "$running" = yes ]; then su-exec postgres pg_ctl -D "$work/pg" -m immediate -w stop >/dev/null 2>&1 || true; fi
    rm -rf "$work"
}
trap cleanup EXIT
su-exec postgres initdb -D "$work/pg" -A trust --no-instructions >/dev/null 2>&1
su-exec postgres pg_ctl -D "$work/pg" -o "-c listen_addresses='' -c unix_socket_directories=$work/sock -p 65431" -w start >/dev/null 2>&1
running=yes
createdb -h "$work/sock" -p 65431 -U postgres example
psql -X -v ON_ERROR_STOP=1 -h "$work/sock" -p 65431 -U postgres -d example -c \
    "CREATE TABLE fixture (id int PRIMARY KEY, value text NOT NULL); INSERT INTO fixture VALUES (1, 'backup data');" >/dev/null
dump="$work/leadcob-fixture.dump"
pg_dump -h "$work/sock" -p 65431 -U postgres -F c -f "$dump" example
su-exec postgres pg_ctl -D "$work/pg" -m immediate -w stop >/dev/null 2>&1
running=no
export RESTIC_REPOSITORY="$work/restic"
export RESTIC_PASSWORD="test-only-not-for-production"
restic init >/dev/null
restic backup "$dump" --tag leadcob >/dev/null
sh /railway-verify-restore.sh "$dump" | tee "$work/result.txt"
grep -q "RESTAURACAO_AUTOMATICA_OK" "$work/result.txt"
printf 'tampered' > "$work/leadcob-tampered.dump"
if sh /railway-verify-restore.sh "$work/leadcob-tampered.dump" >"$work/error.txt" 2>&1; then
    echo "TAMPER DETECTION FAILED" >&2
    exit 1
fi
grep -q "digest mismatch" "$work/error.txt"
echo "CI: restore and tamper detection passed."
