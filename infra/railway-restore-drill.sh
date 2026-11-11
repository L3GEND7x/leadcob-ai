#!/bin/sh
# Ensaio de restauração: baixa o snapshot Restic mais recente (etiqueta leadcob) e o restaura em um
# banco PostgreSQL ISOLADO, informado por RESTORE_PG*. Nunca grava no banco de produção:
# - recusa destino igual ao banco de produção (PGHOST/PGPORT/PGDATABASE, quando definidos);
# - recusa destino que já tenha tabelas;
# - apaga as variáveis PG* de produção antes de chamar pg_restore/psql.
set -eu
umask 077

. "$(dirname "$0")/railway-backup-lib.sh"

for required in RESTORE_PGHOST RESTORE_PGUSER RESTORE_PGPASSWORD RESTORE_PGDATABASE; do
  eval "value=\${$required:-}"
  [ -n "$value" ] || fail "variável ausente ou vazia: $required (banco isolado do ensaio)"
done
[ "${RESTORE_CONFIRM_ISOLATED:-}" = "sim" ] || \
  fail 'defina RESTORE_CONFIRM_ISOLATED=sim para confirmar que RESTORE_PG* aponta para um banco de ensaio, não o de produção.'
check_restic_config

restore_port=${RESTORE_PGPORT:-5432}
if [ -n "${PGHOST:-}" ] && [ "$RESTORE_PGHOST" = "$PGHOST" ] && [ "$restore_port" = "${PGPORT:-5432}" ] && \
   [ "$RESTORE_PGDATABASE" = "${PGDATABASE:-}" ]; then
  fail 'RESTORE_PG* aponta para o mesmo servidor e banco de produção (PGHOST/PGPORT/PGDATABASE). Ensaio cancelado.'
fi
# A partir daqui só o banco de ensaio é acessível pelas ferramentas do PostgreSQL.
unset PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE DATABASE_URL 2>/dev/null || true
export PGHOST="$RESTORE_PGHOST" PGPORT="$restore_port" PGUSER="$RESTORE_PGUSER" \
       PGPASSWORD="$RESTORE_PGPASSWORD" PGDATABASE="$RESTORE_PGDATABASE"

existing=$(psql -X -v ON_ERROR_STOP=1 -tAc "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")
if [ "$existing" != "0" ]; then
  fail "o banco de ensaio já tem $existing tabela(s). Use um banco vazio: o ensaio não apaga nada."
fi

temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
echo 'Etapa 1/4: snapshot mais recente com a etiqueta leadcob.'
restic snapshots --tag leadcob --latest 1
echo 'Etapa 2/4: baixando o snapshot (o Restic confere o hash de cada bloco).'
restic restore latest --tag leadcob --target "$temporary/restaurado"
dump=$(find "$temporary/restaurado" -type f -name 'leadcob-*.dump' | sort | tail -n 1)
[ -n "$dump" ] || fail 'o snapshot não contém arquivo leadcob-*.dump.'
pg_restore --list "$dump" >/dev/null
echo "Dump recuperado: $(basename "$dump"), $(wc -c < "$dump" | tr -d ' ') bytes, sha256 $(sha256sum "$dump" | cut -c1-16)…"

echo 'Etapa 3/4: restaurando no banco de ensaio.'
pg_restore --no-owner --no-acl --exit-on-error --dbname="$RESTORE_PGDATABASE" "$dump"

echo 'Etapa 4/4: conferindo o banco restaurado (linhas por tabela).'
# Contagem exata de cada tabela do esquema public; o resultado deve ser comparado com o painel.
psql -X -v ON_ERROR_STOP=1 -tA -F ' ' <<'SQL' > "$temporary/contagens"
SELECT format('SELECT %L, count(*) FROM %I.%I', tablename, schemaname, tablename)
FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename
\gexec
SQL
[ -s "$temporary/contagens" ] || fail 'nenhuma tabela foi restaurada.'
sed 's/^/  /' "$temporary/contagens"
if grep -q '^alembic_version ' "$temporary/contagens"; then
  echo "  versão do esquema (alembic): $(psql -X -tAc 'SELECT version_num FROM alembic_version')"
fi
echo 'ENSAIO DE RESTAURAÇÃO CONCLUÍDO: snapshot baixado, dump íntegro e restaurado sem erro no banco isolado.'
echo 'Depois de conferir as contagens, apague o banco de ensaio (ele contém cópia dos dados de produção).'
