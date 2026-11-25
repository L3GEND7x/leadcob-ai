"""IP do visitante para limitar tentativas de login.

Atrás de um proxy (Railway), `request.client.host` é o endereço interno do proxy e muda a cada requisição, o
que espalha as tentativas de senha por vários contadores. Quando a conexão vem de uma rede listada em
TRUSTED_PROXY_CIDRS, usa-se o cabeçalho X-Real-IP, que a Railway documenta como o IP do cliente. Sem a
configuração (padrão), nenhum cabeçalho é aceito e o comportamento é o de antes.
"""
import ipaddress

from app.core.config import settings


def _networks():
    nets = []
    for item in (settings.trusted_proxy_cidrs or "").split(","):
        item = item.strip()
        if item:
            try:
                nets.append(ipaddress.ip_network(item, strict=False))
            except ValueError:
                continue   # entrada inválida é ignorada: nunca amplia a confiança
    return nets


def client_ip(request) -> str:
    peer = request.client.host if request.client else "unknown"
    nets = _networks()
    if not nets:
        return peer
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if not any(peer_ip in net for net in nets):
        return peer   # conexão direta, fora do proxy: o cabeçalho não é confiável
    header = (request.headers.get("x-real-ip") or "").strip()
    try:
        return str(ipaddress.ip_address(header))
    except ValueError:
        return peer   # cabeçalho ausente ou inválido: cai no endereço do proxy
