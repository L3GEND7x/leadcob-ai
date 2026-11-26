"""Exercise HTTP wire encodings, not only pre-decoded mock text responses."""
import gzip
import time
import zlib

import httpx
import pytest

from app.collectors.site_contacts import DiscoveryUnavailable, discover
from app.services.safe_http import bounded_get


def encoded_response(body, encoding):
    wire = gzip.compress(body) if encoding == "gzip" else zlib.compress(body)
    return httpx.Response(200, stream=httpx.ByteStream(wire), headers={
        "content-encoding": encoding, "content-length": str(len(wire)),
        "content-type": "text/html; charset=utf-8",
    })


@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
def test_compressed_robots_and_html_preserve_published_contacts(encoding):
    seen = []
    def handler(request):
        seen.append(request.url.path)
        body = (b"User-agent: *\nDisallow: /privado\n" if request.url.path == "/robots.txt"
                else b'<p>contato@empresa.example</p><a href="/privado/contato">Contato</a>')
        return encoded_response(body, encoding)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = discover("https://empresa.example/", client=client)
    assert seen == ["/robots.txt", "/"]
    assert result["emails"] == [{"email": "contato@empresa.example", "source_url": "https://empresa.example/"}]
    assert result["reason_codes"] == ["robots_denied"]


@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
def test_decoded_response_has_matching_headers_and_body(encoding):
    body = "Contato institucional — Manaus".encode()
    with httpx.Client(transport=httpx.MockTransport(lambda r: encoded_response(body, encoding))) as client:
        response = bounded_get(client, "https://empresa.example/", "empresa.example", time.monotonic()+5)
    assert response.content == body
    assert response.text == body.decode()
    assert "content-encoding" not in response.headers
    assert int(response.headers["content-length"]) == len(body)
    assert str(response.url) == "https://empresa.example/"


def test_decoded_size_limit_cannot_be_bypassed_by_compression():
    with httpx.Client(transport=httpx.MockTransport(lambda r: encoded_response(b"x"*4096, "gzip"))) as client:
        with pytest.raises(ValueError, match="Limite de tamanho"):
            bounded_get(client, "https://empresa.example/", "empresa.example", time.monotonic()+5, max_bytes=128)


def test_malformed_compressed_robots_fails_closed_with_safe_diagnostic():
    seen = []
    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, stream=httpx.ByteStream(b"invalid gzip private content"),
                              headers={"content-encoding": "gzip"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DiscoveryUnavailable) as exc:
            discover("https://empresa.example/", client=client)
    assert exc.value.code == "robots_content_decoding_error"
    assert "private content" not in str(exc.value)
    assert seen == ["/robots.txt"]
