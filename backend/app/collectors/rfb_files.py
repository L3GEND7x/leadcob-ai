"""Acesso aos arquivos de dados abertos do CNPJ (Receita Federal).

Fonte (verificada em 09/11/2026): compartilhamento público Nextcloud
https://arquivos.receitafederal.gov.br/index.php/s/gn672Ad4CF8N6TK
(o endereço antigo /dados/cnpj/dados_abertos_cnpj/ responde 404).
WebDAV público: /public.php/webdav/Dados/Cadastros/CNPJ/AAAA-MM/
com usuário = token do compartilhamento e senha vazia.

Os ZIPs são lidos por HTTP Range (o servidor responde 206): o membro CSV é
descompactado em fluxo, sem gravar os arquivos (≈ 7 GB por publicação) em disco.
"""
from __future__ import annotations

import io
import os
import re
import time
import zipfile
from urllib.parse import unquote

import httpx

HOST = os.getenv("RFB_FILES_HOST", "https://arquivos.receitafederal.gov.br").rstrip("/")
SHARE_TOKEN = os.getenv("RFB_SHARE_TOKEN", "gn672Ad4CF8N6TK")
DAV_ROOT = f"{HOST}/public.php/webdav"
CNPJ_DIR = os.getenv("RFB_CNPJ_DIR", "Dados/Cadastros/CNPJ").strip("/")
USER_AGENT = "LeadCobAI/0.3 (dados abertos CNPJ)"


def client(timeout: float = 60.0) -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(timeout, connect=20.0), auth=(SHARE_TOKEN, ""), headers={"User-Agent": USER_AGENT},
                        follow_redirects=True)


def list_dir(path: str, http: httpx.Client | None = None) -> list[tuple[str, int | None]]:
    """PROPFIND Depth 1 → [(nome, tamanho)] (pastas terminam em '/')."""
    own = http is None
    http = http or client()
    try:
        url = f"{DAV_ROOT}/{path.strip('/')}/" if path.strip("/") else f"{DAV_ROOT}/"
        r = http.request("PROPFIND", url, headers={"Depth": "1"})
        r.raise_for_status()
    finally:
        if own:
            http.close()
    out = []
    for resp in re.findall(r"<d:response>(.*?)</d:response>", r.text, re.S):
        href = unquote(re.search(r"<d:href>([^<]*)", resp).group(1))
        name = href.rstrip("/").split("/")[-1] + ("/" if href.endswith("/") else "")
        size = re.search(r"<d:getcontentlength>(\d+)", resp)
        if href.rstrip("/") == f"/public.php/webdav/{path.strip('/')}".rstrip("/"):
            continue  # a própria pasta
        out.append((name, int(size.group(1)) if size else None))
    return out


def latest_release(http: httpx.Client | None = None) -> str:
    months = sorted(n.rstrip("/") for n, _ in list_dir(CNPJ_DIR or "", http) if re.fullmatch(r"\d{4}-\d{2}/", n))
    if not months:
        raise RuntimeError("Nenhuma publicação AAAA-MM encontrada no compartilhamento da Receita.")
    return months[-1]


def file_url(release: str, name: str) -> str:
    return "/".join(x for x in (DAV_ROOT, CNPJ_DIR, release, name) if x)


class HttpRangeFile(io.RawIOBase):
    """Arquivo remoto somente-leitura e buscável via HTTP Range.

    Lê em blocos (padrão 4 MiB) para equilibrar número de requisições e memória.
    """

    def __init__(self, url: str, http: httpx.Client, block: int = 4 * 1024 * 1024, attempts: int = 4):
        super().__init__()
        self.url, self.http, self.block, self.attempts = url, http, block, attempts
        # Sondagem com 64 KiB: o servidor da Receita trava com "bytes=0-0"
        # (verificado em 09/11/2026), mas responde normalmente a blocos maiores.
        head = self._get(0, 65535)
        total = head.headers.get("content-range", "").split("/")[-1]
        if head.status_code != 206 or not total.isdigit():
            raise RuntimeError(f"Servidor não aceitou leitura parcial (HTTP {head.status_code}).")
        self.size = int(total)
        self.pos = 0
        self._buf_start, self._buf = 0, head.content
        self.bytes_fetched = len(head.content)

    def _get(self, start: int, end: int) -> httpx.Response:
        last = None
        for i in range(self.attempts):
            try:
                r = self.http.get(self.url, headers={"Range": f"bytes={start}-{end}"})
                if r.status_code in (200, 206):
                    return r
                last = RuntimeError(f"HTTP {r.status_code}")
            except httpx.TransportError as exc:  # inclui timeouts
                last = exc
            time.sleep(2 ** i)
        raise RuntimeError(f"Falha ao ler {self.url} [{start}-{end}]: {last}")

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence]
        self.pos = max(0, base + offset)
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        rel = self.pos - self._buf_start
        if not (0 <= rel < len(self._buf)):
            end = min(self.pos + max(self.block, len(b)) - 1, self.size - 1)
            r = self._get(self.pos, end)
            self._buf_start, self._buf = self.pos, r.content
            self.bytes_fetched += len(r.content)
            rel = 0
        n = min(len(b), len(self._buf) - rel)
        b[:n] = self._buf[rel:rel + n]
        self.pos += n
        return n


def iter_csv_rows(fileobj, encoding: str = "latin-1"):
    """Linhas do CSV da Receita: separador ';', campos entre aspas, sem cabeçalho."""
    import csv
    with zipfile.ZipFile(fileobj) as zf:
        member = zf.namelist()[0]
        with zf.open(member) as raw:
            text = io.TextIOWrapper(raw, encoding=encoding, newline="")
            yield from csv.reader(text, delimiter=";", quotechar='"')


def iter_remote_rows(release: str, name: str, http: httpx.Client | None = None, block: int = 4 * 1024 * 1024):
    own = http is None
    http = http or client()
    try:
        f = HttpRangeFile(file_url(release, name), http, block=block)
        yield from iter_csv_rows(io.BufferedReader(f, buffer_size=1024 * 1024))
    finally:
        if own:
            http.close()
