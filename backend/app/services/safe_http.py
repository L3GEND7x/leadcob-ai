"""Bounded public HTTP access, including DNS pinning at connection time."""
import ipaddress
import socket
import ssl
import time
from urllib.parse import urlparse, urljoin

import httpcore
import httpx


def validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use uma URL pública HTTP(S), sem credenciais.")
    if parsed.port not in (None, 80, 443):
        raise ValueError("Porta do site não permitida.")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Destino interno bloqueado.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return parsed
    if not address.is_global:
        raise ValueError("Destino interno bloqueado.")
    return parsed


class PublicNetworkBackend(httpcore.SyncBackend):
    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        # The socket connects to this validated numeric IP, so DNS is not resolved again.
        addresses = {row[4][0] for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise httpcore.ConnectError("Destino privado ou reservado bloqueado")
        return super().connect_tcp(sorted(addresses)[0], port, timeout, local_address, socket_options)


class PublicTransport(httpx.HTTPTransport):
    def __init__(self):
        super().__init__()
        self._pool.close()
        self._pool = httpcore.ConnectionPool(ssl_context=ssl.create_default_context(),
                                             network_backend=PublicNetworkBackend(), max_connections=4)


def public_client():
    return httpx.Client(transport=PublicTransport(), trust_env=False, follow_redirects=False,
                        timeout=8, headers={"User-Agent": "LeadCobAI/0.6 (institutional contact research)"})


def bounded_get(client, url, allowed_host, deadline, max_bytes=400_000):
    for _ in range(4):
        parsed = validate_url(url)
        if parsed.hostname.lower().removeprefix("www.") != allowed_host.lower().removeprefix("www."):
            raise ValueError("Redirecionamento para outro domínio bloqueado.")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("Tempo máximo de leitura excedido.")
        with client.stream("GET", url, follow_redirects=False, timeout=min(8, remaining)) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise ValueError("Redirecionamento sem destino.")
                url = urljoin(url, location)
                continue
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > max_bytes or time.monotonic() > deadline:
                    raise ValueError("Limite de tamanho ou tempo da página excedido.")
                chunks.append(chunk)
            return httpx.Response(response.status_code, headers=response.headers,
                                  content=b"".join(chunks), request=httpx.Request("GET", url))
    raise ValueError("Limite de redirecionamentos excedido.")
