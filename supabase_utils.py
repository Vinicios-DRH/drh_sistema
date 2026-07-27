import os
from typing import Any

from supabase import create_client as supabase_create_client


def create_supabase_client(supabase_url: str | None, supabase_key: str | None) -> Any | None:
    if not supabase_url or not supabase_key:
        return None

    try:
        return supabase_create_client(supabase_url, supabase_key)
    except ImportError as exc:
        message = str(exc)
        if "SOCKS proxy" not in message or "socksio" not in message:
            raise

        for proxy_var in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            os.environ.pop(proxy_var, None)

        return supabase_create_client(supabase_url, supabase_key)
