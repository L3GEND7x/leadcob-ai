"""Gera ADMIN_PASSWORD_HASH para o LeadCob AI sem instalar o projeto (só Python 3).

Uso, no seu computador:  python3 scripts/gerar_hash_senha.py
A senha é digitada sem aparecer na tela, nunca é gravada e não sai do computador.
Copie só a linha que começa com pbkdf2_sha256. e cole em ADMIN_PASSWORD_HASH na Railway.
Mesmo formato de backend/app/core/security.py (PBKDF2-SHA256, 600.000 iterações, sal aleatório).
"""
import getpass
import hashlib
import secrets
import sys

MINIMO = 14


def gerar(senha: str) -> str:
    sal = secrets.token_hex(16)
    return f"pbkdf2_sha256.{sal}.{hashlib.pbkdf2_hmac('sha256', senha.encode(), sal.encode(), 600000).hex()}"


def main() -> int:
    senha = getpass.getpass(f"Nova senha do proprietário (mínimo {MINIMO} caracteres): ")
    if len(senha) < MINIMO:
        print(f"Senha curta: use pelo menos {MINIMO} caracteres.", file=sys.stderr)
        return 1
    if senha != getpass.getpass("Repita a senha: "):
        print("As duas senhas são diferentes. Nada foi gerado.", file=sys.stderr)
        return 1
    print(gerar(senha))
    return 0


if __name__ == "__main__":
    sys.exit(main())
