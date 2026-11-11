#!/bin/sh
# Conferência das variáveis do Restic e da chave S3, compartilhada pelo backup e pelo ensaio de
# restauração. Nenhuma mensagem imprime valor de variável sensível: só nome, tamanho e tipo de problema.

fail() {
  echo "ERRO de configuração: $*" >&2
  exit 1
}

check_restic_config() {
for required in RESTIC_REPOSITORY RESTIC_PASSWORD AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY; do
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
}
