"""Restricted public-web fetcher with lightweight readable-text extraction."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import re
import socket
import ssl
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import httpx

from novelforge.core.schemas import FetchedWebPage


DEFAULT_FETCH_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_RESPONSE_BYTES = 2_000_000
DEFAULT_MAX_REDIRECTS = 5
ALLOWED_CONTENT_TYPES = {
    "text/html",
    "text/plain",
    "application/xhtml+xml",
}


class WebFetchError(RuntimeError):
    """Raised when a public page cannot be downloaded or parsed."""


class WebFetchSecurityError(WebFetchError):
    """Raised when a URL violates the public-network fetch boundary."""


def normalize_web_url(url: str) -> str:
    cleaned = str(url or "").strip()
    try:
        parsed = urlsplit(cleaned)
    except ValueError as exc:
        raise WebFetchSecurityError("网页地址格式无效。") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise WebFetchSecurityError("只允许抓取 http/https 网页。")
    if not parsed.hostname:
        raise WebFetchSecurityError("网页地址缺少有效主机名。")
    if parsed.username or parsed.password:
        raise WebFetchSecurityError("网页地址不能包含用户名或密码。")
    try:
        host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
        port = parsed.port
    except (UnicodeError, ValueError) as exc:
        raise WebFetchSecurityError("网页地址包含无效的主机名或端口。") from exc
    if not host:
        raise WebFetchSecurityError("网页地址缺少有效主机名。")
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    display_host = f"[{host}]" if ":" in host else host
    netloc = display_host if port is None or default_port else f"{display_host}:{port}"
    path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
    query = quote(parsed.query, safe="=&%/:?@!$'()*+,;~-._")
    return urlunsplit((scheme, netloc, path, query, ""))


def _resolved_addresses(
    host: str,
    port: int,
    resolver: Callable[..., list[tuple]],
) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            rows = resolver(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise WebFetchSecurityError(f"无法解析网页主机：{host}") from exc
        addresses = set()
        for row in rows:
            try:
                addresses.add(ipaddress.ip_address(row[4][0]))
            except (IndexError, ValueError, TypeError):
                continue
        if not addresses:
            raise WebFetchSecurityError(f"网页主机没有可用地址：{host}")
        return addresses
    return {literal}


def validate_public_web_url(
    url: str,
    *,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> str:
    normalized = normalize_web_url(url)
    parsed = urlsplit(normalized)
    host = str(parsed.hostname or "").lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise WebFetchSecurityError("不允许抓取本机地址。")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    for address in _resolved_addresses(host, port, resolver):
        if not address.is_global:
            raise WebFetchSecurityError("不允许抓取内网、保留或本机地址。")
    return normalized


class _ReadableHTMLParser(HTMLParser):
    _SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "template"}
    _BLOCK_TAGS = {
        "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt",
        "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5",
        "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre",
        "section", "table", "tbody", "td", "th", "thead", "tr", "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.description = ""
        self._skip_depth = 0
        self._title_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if lowered == "title":
            self._title_depth += 1
        if lowered == "meta":
            values = {str(key).lower(): str(value or "") for key, value in attrs}
            key = values.get("name", "").lower() or values.get("property", "").lower()
            if key in {"description", "og:description"} and not self.description:
                self.description = values.get("content", "").strip()
        if lowered in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in self._SKIP_TAGS:
            self._skip_depth = max(self._skip_depth - 1, 0)
            return
        if self._skip_depth:
            return
        if lowered == "title":
            self._title_depth = max(self._title_depth - 1, 0)
        if lowered in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        cleaned = " ".join(str(data or "").split())
        if not cleaned:
            return
        if self._title_depth:
            self.title_parts.append(cleaned)
        self.parts.append(cleaned)

    def readable_text(self) -> str:
        raw = unescape(" ".join(self.parts))
        raw = re.sub(r"[ \t\f\v]+", " ", raw)
        raw = re.sub(r" *\n *", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()

    def page_title(self) -> str:
        return " ".join(self.title_parts).strip()


def _decode_body(body: bytes, content_type_header: str) -> str:
    match = re.search(r"charset\s*=\s*['\"]?([^;\s'\"]+)", str(content_type_header or ""), re.I)
    encoding = match.group(1).strip() if match else "utf-8"
    try:
        return body.decode(encoding, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _read_limited_body(response: httpx.Response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise WebFetchError(f"网页正文超过允许大小（{max_bytes} 字节）。")
        chunks.append(chunk)
    return b"".join(chunks)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, connect_ip: str, *, timeout: float) -> None:
        super().__init__(host, port=port, timeout=timeout)
        self._connect_ip = connect_ip

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._connect_ip, self.port),
            self.timeout,
            self.source_address,
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, connect_ip: str, *, timeout: float) -> None:
        context = ssl.create_default_context()
        context.set_alpn_protocols(["http/1.1"])
        super().__init__(host, port=port, timeout=timeout, context=context)
        self._connect_ip = connect_ip

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._connect_ip, self.port),
            self.timeout,
            self.source_address,
        )
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


def _public_target_addresses(
    url: str,
    resolver: Callable[..., list[tuple]],
) -> tuple[str, list[str]]:
    normalized = normalize_web_url(url)
    parsed = urlsplit(normalized)
    host = str(parsed.hostname or "").lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise WebFetchSecurityError("不允许抓取本机地址。")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = _resolved_addresses(host, port, resolver)
    if any(not address.is_global for address in addresses):
        raise WebFetchSecurityError("不允许抓取内网、保留或本机地址。")
    return normalized, sorted(str(address) for address in addresses)


def _send_pinned_request(
    url: str,
    *,
    max_bytes: int,
    resolver: Callable[..., list[tuple]],
) -> tuple[int, dict[str, str], bytes]:
    """Resolve once, validate every address, then connect directly to one approved IP."""

    normalized, addresses = _public_target_addresses(url, resolver)
    parsed = urlsplit(normalized)
    host = str(parsed.hostname or "")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    request_target = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
    last_error: Exception | None = None
    for address in addresses:
        connection: http.client.HTTPConnection
        if parsed.scheme == "https":
            connection = _PinnedHTTPSConnection(
                host,
                port,
                address,
                timeout=DEFAULT_FETCH_TIMEOUT_SECONDS,
            )
        else:
            connection = _PinnedHTTPConnection(
                host,
                port,
                address,
                timeout=DEFAULT_FETCH_TIMEOUT_SECONDS,
            )
        try:
            connection.request(
                "GET",
                request_target,
                headers={
                    "User-Agent": "NovelForge/0.7 WebResearch (+local research import)",
                    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
                    "Accept-Encoding": "identity",
                },
            )
            response = connection.getresponse()
            headers = {str(key).lower(): str(value) for key, value in response.getheaders()}
            body = b""
            if 200 <= response.status < 300:
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise WebFetchError(f"网页正文超过允许大小（{max_bytes} 字节）。")
                    chunks.append(chunk)
                body = b"".join(chunks)
            return int(response.status), headers, body
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            last_error = exc
        finally:
            connection.close()
    raise WebFetchError(f"网页抓取失败：{last_error or '没有可连接的公网地址'}")


def _send_injected_httpx_request(
    client: httpx.Client,
    url: str,
    *,
    max_bytes: int,
) -> tuple[int, dict[str, str], bytes]:
    response = client.send(
        client.build_request("GET", url),
        stream=True,
        follow_redirects=False,
    )
    try:
        body = _read_limited_body(response, max_bytes) if 200 <= response.status_code < 300 else b""
        return int(response.status_code), {key.lower(): value for key, value in response.headers.items()}, body
    finally:
        response.close()


def fetch_web_page(
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
    client: httpx.Client | None = None,
) -> FetchedWebPage:
    """Fetch one public page without cookies, credentials, or automatic redirects."""

    if max_bytes < 1:
        raise ValueError("网页大小限制必须大于 0。")
    if max_redirects < 0:
        raise ValueError("网页重定向限制不能小于 0。")
    current_url = validate_public_web_url(url, resolver=resolver)
    status_code = 0
    response_headers: dict[str, str] = {}
    body = b""
    try:
        for redirect_index in range(max_redirects + 1):
            if client is None:
                status_code, response_headers, body = _send_pinned_request(
                    current_url,
                    max_bytes=max_bytes,
                    resolver=resolver,
                )
            else:
                status_code, response_headers, body = _send_injected_httpx_request(
                    client,
                    current_url,
                    max_bytes=max_bytes,
                )
            if status_code in {301, 302, 303, 307, 308}:
                location = response_headers.get("location", "").strip()
                if not location:
                    raise WebFetchError("网页返回了缺少目标地址的重定向。")
                if redirect_index >= max_redirects:
                    raise WebFetchError("网页重定向次数过多。")
                current_url = validate_public_web_url(urljoin(current_url, location), resolver=resolver)
                continue
            if status_code < 200 or status_code >= 300:
                raise WebFetchError(f"网页请求失败（HTTP {status_code}）。")
            content_encoding = response_headers.get("content-encoding", "").strip().lower()
            if content_encoding not in {"", "identity"}:
                raise WebFetchError(f"网页返回了不受支持的内容编码：{content_encoding}")
            content_type_header = response_headers.get("content-type", "")
            content_type = content_type_header.split(";", 1)[0].strip().lower()
            if content_type not in ALLOWED_CONTENT_TYPES:
                raise WebFetchError(f"暂不支持该网页内容类型：{content_type or 'unknown'}")
            break
        else:
            raise WebFetchError("网页重定向次数过多。")
    except (httpx.HTTPError, OSError) as exc:
        raise WebFetchError(f"网页抓取失败：{exc}") from exc

    decoded = _decode_body(body, content_type_header)
    if content_type in {"text/html", "application/xhtml+xml"}:
        parser = _ReadableHTMLParser()
        try:
            parser.feed(decoded)
            parser.close()
        except Exception as exc:
            raise WebFetchError(f"网页正文解析失败：{exc}") from exc
        text = parser.readable_text()
        title = parser.page_title()
        description = parser.description
    else:
        text = decoded.strip()
        title = ""
        description = ""
    if not text:
        raise WebFetchError("网页没有可导入的文本正文。")

    final_url = normalize_web_url(current_url)
    fallback_title = str(urlsplit(final_url).hostname or "网络资料")
    return FetchedWebPage(
        requested_url=normalize_web_url(url),
        final_url=final_url,
        title=(title or fallback_title)[:500],
        description=description[:2000],
        text=text,
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        status_code=status_code,
        content_type=content_type,
        byte_count=len(body),
        metadata={
            "etag": response_headers.get("etag", ""),
            "last_modified": response_headers.get("last-modified", ""),
        },
    )
