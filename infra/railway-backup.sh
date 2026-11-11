#!/bin/sh
set -eu
umask 077

# Nenhuma mensagem deste script imprime o valor de uma variável sensível: só o nome,
# o tamanho e o tipo de problema encontrado.

fail() {
  echo "ERRO de configuração: $*" >&2
  exit 1
}

for required in PGHOST PGUSER PGPASSWORD PGDATABASE RESTIC_REPOSITORY RESTIC_PASSWORD AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY; do
  eval "value=\${$required:-}"
  if [ -z "$value" ]; then
    fail "variável ausente ou vazia: $required"
  fi
done

# Quantidade de bytes do valor que estão fora do ASCII visível (espaço incluído no visível).
bytes_outside_printable() {
  printf '%s' "$1" | LC_ALL=C tr -d ' -~' | wc -c | tr -d ' '
}

has_line_break() {
  [ "$(printf '%s' "$1" | LC_ALL=C tr -d -c '\n\r' | wc -c | tr -d ' ')" -gt 0 ]
}

# Valores colados com quebra de linha (\n ou \r) fazem o cliente HTTP do Restic recusar o
# cabeçalho Authorization ("invalid header field value"). Não corrigimos em silêncio: o valor
# certo deve ser gravado de novo na Railway.
check_clean() {
  name=$1
  eval "value=\${$name:-}"
  [ -n "$value" ] || return 0
  length=$(printf '%s' "$value" | wc -c | tr -d ' ')
  if has_line_break "$value"; then
    fail "$name contém quebra de linha ($length bytes no total). Apague o valor na Railway e cole de novo só o valor, em uma linha."
  fi
  odd=$(bytes_outside_printable "$value")
  if [ "$odd" -gt 0 ]; then
    fail "$name contém $odd byte(s) de controle ou fora do ASCII ($length bytes no total). Cole de novo só o valor."
  fi
  case "$value" in
    ' '*|*' ') fail "$name começa ou termina com espaço ($length bytes no total)." ;;
  esac
}

for name in AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY RESTIC_REPOSITORY RESTIC_PASSWORD AWS_DEFAULT_REGION AWS_REGION; do
  check_clean "$name"
done

if [ -n "${AWS_SESSION_TOKEN:-}" ]; then
  fail 'AWS_SESSION_TOKEN está definida. Chaves de aplicativo da Backblaze B2 não usam token de sessão: remova essa variável.'
fi

key_id_length=$(printf '%s' "$AWS_ACCESS_KEY_ID" | wc -c | tr -d ' ')
case "$AWS_ACCESS_KEY_ID" in
  *[!A-Za-z0-9]*)
    fail "AWS_ACCESS_KEY_ID deve ter só letras e números (o keyID da chave de aplicativo), sem rótulo como 'keyID:', aspas ou espaços ($key_id_length caracteres recebidos)." ;;
esac
if [ "$key_id_length" -lt 10 ] || [ "$key_id_length" -gt 64 ]; then
  fail "AWS_ACCESS_KEY_ID tem $key_id_length caracteres; isso não parece um keyID. Confira se não foi colado o nome da chave ou outro texto."
fi
case "$AWS_SECRET_ACCESS_KEY" in
  *' '*) fail 'AWS_SECRET_ACCESS_KEY contém espaço. Cole só a applicationKey.' ;;
esac
if [ "$AWS_ACCESS_KEY_ID" = "$AWS_SECRET_ACCESS_KEY" ]; then
  fail 'AWS_ACCESS_KEY_ID e AWS_SECRET_ACCESS_KEY têm o mesmo valor: o primeiro é o keyID, o segundo é a applicationKey.'
fi

case "$RESTIC_REPOSITORY" in
  s3:https://*/?*) ;;
  s3:https://*) fail 'RESTIC_REPOSITORY sem nome do bucket. Formato: s3:https://<endpoint-S3>/<bucket>' ;;
  *) fail 'RESTIC_REPOSITORY deve usar S3 com TLS. Formato: s3:https://<endpoint-S3>/<bucket>' ;;
esac
echo "Configuração conferida (keyID com $key_id_length caracteres alfanuméricos; nenhum valor é exibido)."

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
