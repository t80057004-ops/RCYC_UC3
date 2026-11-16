"""Diagnostic script to check Informatica connection health via /api/health/informatica."""

from __future__ import annotations

import json
import os
import sys
import httpx


def main() -> int:
    base_url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.getenv("MARIS_BASE_URL", "http://127.0.0.1:3000")
    ).rstrip("/")
    endpoint = f"{base_url}/api/health/informatica"

    try:
        response = httpx.get(endpoint, timeout=15.0)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"ERROR: Failed to query {endpoint}: {exc}", file=sys.stderr)
        return 2

    configured = bool(payload.get("configured", False))
    login_ok = bool(payload.get("login_ok", False))
    search_ok = bool(payload.get("search_ok", False))
    entity = str(payload.get("entity", ""))

    print(f"endpoint   : {endpoint}")
    print(f"entity     : {entity}")
    print(f"configured : {configured}")
    print(f"login_ok   : {login_ok}")
    print(f"search_ok  : {search_ok}")
    print(
        json.dumps(
            {
                "configured": configured,
                "login_ok": login_ok,
                "search_ok": search_ok,
                "entity": entity,
            }
        )
    )

    return 0 if (configured and login_ok and search_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
