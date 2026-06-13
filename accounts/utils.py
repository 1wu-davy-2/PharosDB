"""
Accounts utility — client IP extraction from request.
Supports both direct connections and reverse-proxy (X-Forwarded-For).
"""
from typing import Dict, List


def get_client_ip(request) -> str:
    """Resolve the originating client IP.

    Priority order:
    1. X-Forwarded-For header (leftmost entry = original client)
    2. REMOTE_ADDR (direct connection or dev server)
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ips = [ip.strip() for ip in x_forwarded_for.split(",") if ip.strip()]
        if ips:
            return ips[0]
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def get_x_forwarded_chain(request) -> List[str]:
    """Return the full X-Forwarded-For chain (may be empty)."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return [ip.strip() for ip in x_forwarded_for.split(",") if ip.strip()]


def get_client_ip_info(request) -> Dict:
    """Return a detailed breakdown of the client IP resolution.

    Returns:
        {
            "remote_addr": "<socket peer>",
            "x_forwarded_chain": [...],
            "resolved_ip": "<the IP we actually bind to the token>",
        }
    """
    return {
        "remote_addr": request.META.get("REMOTE_ADDR", "0.0.0.0"),
        "x_forwarded_chain": get_x_forwarded_chain(request),
        "resolved_ip": get_client_ip(request),
    }
