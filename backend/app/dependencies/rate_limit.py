"""Shared rate limiter instance for the application."""
from fastapi import Request
from slowapi import Limiter


def get_client_ip(request: Request) -> str:
    """
    Get the real client IP address.

    Priority:
      1. CF-Connecting-IP (Cloudflare) — most reliable behind Cloudflare proxy
      2. X-Forwarded-For — standard proxy header (set by Nginx)
      3. request.client.host — direct connection fallback
    """
    # Cloudflare sets this header with the real client IP
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    # Fallback: X-Forwarded-For (first IP in the chain)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can be a comma-separated list; take the first (original client)
        return forwarded_for.split(",")[0].strip()

    # Last resort: direct connection IP
    if request.client:
        return request.client.host

    return "0.0.0.0"


limiter = Limiter(
    key_func=get_client_ip,
    enabled=True,
    default_limits=[],
)