"""Validation for the user-editable Hacker AI base URL.

The base URL is a stored setting, so without validation an operator typo (or a
stolen session) could point the server at an internal address. Requests are
therefore restricted to HTTPS public hosts. Local HTTP is only permitted when
HACKER_AI_ALLOW_INSECURE_BASE_URL=1, which exists for local gateways.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.config import settings

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
BLOCKED_SUFFIXES = (".local", ".localhost", ".internal", ".home.arpa", ".lan")


class InvalidBaseURL(ValueError):
    """Raised when a base URL is not an acceptable outbound target."""


def _is_local_name(host: str) -> bool:
    lowered = host.lower().rstrip(".")
    return lowered in LOCAL_HOSTS or lowered.endswith(BLOCKED_SUFFIXES)


def _literal_ip(host: str):
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def validate_base_url(raw: str) -> str:
    """Return a normalised base URL or raise InvalidBaseURL with a readable reason."""
    value = (raw or "").strip()
    if not value:
        raise InvalidBaseURL("Base URL is required.")
    if any(char.isspace() for char in value):
        raise InvalidBaseURL("Base URL cannot contain spaces.")
    parsed = urlparse(value)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise InvalidBaseURL("Base URL must start with https:// (or http:// for a local gateway).")
    if parsed.username or parsed.password:
        raise InvalidBaseURL("Base URL cannot contain a username or password.")
    if parsed.query or parsed.fragment:
        raise InvalidBaseURL("Base URL cannot contain a query string or fragment.")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise InvalidBaseURL("Base URL is missing a hostname.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise InvalidBaseURL("Base URL has an invalid port.") from exc
    if port is not None and not 1 <= port <= 65535:
        raise InvalidBaseURL("Base URL has an invalid port.")

    insecure_ok = settings.allow_insecure_base_url
    if scheme == "http" and not (insecure_ok and _is_local_name(host)):
        raise InvalidBaseURL("Base URL must use https://. Set HACKER_AI_ALLOW_INSECURE_BASE_URL=1 only for a local gateway.")
    if not insecure_ok:
        if _is_local_name(host):
            raise InvalidBaseURL("Base URL cannot point at localhost or a private hostname.")
        address = _literal_ip(host)
        if address is not None and not address.is_global:
            raise InvalidBaseURL("Base URL cannot point at a private or reserved IP address.")

    netloc = parsed.netloc
    path = parsed.path.rstrip("/")
    return f"{scheme}://{netloc}{path}"


def assert_public_url(url: str) -> None:
    """Resolve a URL host and refuse private destinations (defence in depth).

    Called right before an outbound request so a hostname that resolves to an
    internal address is rejected even though it passed the structural check.
    """
    if settings.allow_insecure_base_url:
        return
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host or _is_local_name(host):
        raise InvalidBaseURL("Outbound host is not public.")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise InvalidBaseURL(f"Could not resolve {host}: {exc}") from exc
    for info in infos:
        raw_address = info[4][0]
        address = _literal_ip(raw_address)
        if address is None or not address.is_global:
            raise InvalidBaseURL(f"{host} resolves to a non-public address ({raw_address}).")
