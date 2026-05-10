"""
Browser-like HTTP for crawler/fetch paths (helps with Cloudflare and similar fronts).

Uses ``curl_cffi`` TLS fingerprint impersonation when available; falls back to
``requests`` + ``seo_audit.attach_default_headers`` at call sites for plain installs.
"""

from __future__ import annotations

import os

# Common stable Chrome profile shipped with curl-cffi; override via env if needed.
_IMPERSONATE = (os.environ.get("CURL_CFFI_IMPERSONATE") or "chrome120").strip() or "chrome120"


def make_fetch_session() -> object:
    """
    Prefer ``curl_cffi.requests.Session`` (browser TLS fingerprint).
    Falls back to ``requests.Session`` if curl-cffi is not installed / fails to import.
    """
    force_plain = os.environ.get("GEO_USE_STD_REQUESTS_ONLY", "").strip() in {"1", "true", "yes"}
    if not force_plain:
        try:
            from curl_cffi import requests as cf

            return cf.Session(impersonate=_IMPERSONATE)
        except Exception:
            pass

    import requests

    return requests.Session()
