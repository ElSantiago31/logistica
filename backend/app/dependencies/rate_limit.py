"""Shared rate limiter instance for the application."""
from fastapi import Request
from slowapi import Limiter


def get_client_ip(request: Request) -> str:
    """
    Get the real client IP address (spoof-resistant).

    SECURITY (HIGH-2 fix): Only trust headers that Nginx injects after
    validating the upstream. The previous implementation trusted
    'CF-Connecting-IP' and 'X-Forwarded-For' straight from the client request,
    which allowed an attacker to forge those headers and bypass rate limiting.

    Priority:
      1. X-Real-IP — injected by Nginx (overwritten, not forgeable by client).
                     Nginx resolves the real client IP via 'real_ip_header
                     CF-Connecting-IP' + 'set_real_ip_from <cloudflare ranges>'.
      2. request.client.host — direct connection fallback (local dev without proxy).
    """
    # 1. X-Real-IP: set by Nginx after IP sanitization (not forgeable by client)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # 2. Fallback for local development (no reverse proxy in front)
    if request.client:
        return request.client.host

    return "0.0.0.0"


limiter = Limiter(
    key_func=get_client_ip,
    enabled=True,
    default_limits=[],
)