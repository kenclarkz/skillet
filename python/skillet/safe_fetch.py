"""SSRF-safe HTML fetching for user-supplied recipe URLs — port of safe-fetch.ts."""

from __future__ import annotations

import ipaddress
import re
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
}

MAX_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_REDIRECTS = 5
TIMEOUT_SECONDS = 12

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
)


class FetchError(Exception):
    """User-facing fetch failure with a safe message."""


def _is_private_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return True
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
        return True
    if ip.version == 4:
        # CGNAT 100.64.0.0/10 (is_private on 3.9+, but keep explicit)
        if ip in ipaddress.ip_network("100.64.0.0/10"):
            return True
    return False


def assert_public_url(raw_url: str) -> str:
    """Raise FetchError if the URL is not safe to fetch server-side."""
    try:
        parsed = urlparse(raw_url)
    except ValueError:
        raise FetchError("That does not look like a valid URL.") from None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        if parsed.scheme not in ("http", "https"):
            raise FetchError("Only http and https URLs are supported.")
        raise FetchError("That does not look like a valid URL.")
    hostname = parsed.hostname.lower().strip("[]")
    if hostname in BLOCKED_HOSTNAMES or hostname.endswith(".local") or hostname.endswith(".internal"):
        raise FetchError("That host is not allowed.")
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        if _is_private_address(str(literal)):
            raise FetchError("Private network addresses are not allowed.")
        return raw_url
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise FetchError(f"Could not resolve {hostname}.") from None
    for info in infos:
        address = info[4][0]
        if _is_private_address(address):
            raise FetchError("Private network addresses are not allowed.")
    return raw_url


def safe_fetch_html(raw_url: str) -> dict[str, Any]:
    """Fetch a remote HTML page with size, redirect, and SSRF protections."""
    current = assert_public_url(raw_url)
    headers = {
        "user-agent": USER_AGENT,
        "accept": "text/html,application/xhtml+xml",
        "accept-language": "en-US,en;q=0.9",
    }

    for _ in range(MAX_REDIRECTS + 1):
        try:
            response = requests.get(
                current, headers=headers, allow_redirects=False, timeout=TIMEOUT_SECONDS, stream=True
            )
        except requests.Timeout:
            raise FetchError("The site took too long to respond.") from None
        except requests.RequestException:
            raise FetchError("Could not reach that website.") from None

        try:
            if 300 <= response.status_code < 400:
                location = response.headers.get("location")
                if not location:
                    raise FetchError("The site returned an invalid redirect.")
                current = assert_public_url(urljoin(current, location))
                continue

            if response.status_code >= 400:
                raise FetchError(f"The site responded with {response.status_code}.")

            content_type = response.headers.get("content-type") or ""
            if "html" not in content_type and "xml" not in content_type and content_type != "":
                raise FetchError("That URL is not an HTML page.")

            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                total += len(chunk)
                if total > MAX_BYTES:
                    raise FetchError("That page is too large to import.")
                chunks.append(chunk)
            if not chunks:
                raise FetchError("Empty response from the site.")

            charset_match = re.search(r"charset=([\w-]+)", content_type, re.IGNORECASE)
            charset = (charset_match.group(1) if charset_match else "utf-8").lower()
            if charset == "iso-8859-1":
                charset = "latin-1"
            try:
                html = b"".join(chunks).decode(charset, errors="replace")
            except LookupError:
                html = b"".join(chunks).decode("utf-8", errors="replace")
            return {"html": html, "final_url": current}
        finally:
            response.close()

    raise FetchError("Too many redirects.")
