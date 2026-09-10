"""Read-only live smoke test. Never invokes a state-changing tool.

Run on the server with GATEWAY_TOKEN set and optionally GATEWAY_BASE_URL.
Prints only tool names/outcomes/timing; diagnostic payloads stay in memory.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    base = os.getenv("GATEWAY_BASE_URL", "http://127.0.0.1:18081").rstrip("/")
    token = os.environ["GATEWAY_TOKEN"]
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}

    def request(path: str, data: dict | None = None) -> dict:
        payload = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(base + path, data=payload, headers=headers)
        # Internal localhost diagnostics must never be routed through a proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=35) as response:
            return json.load(response)

    results = []
    for tool in request("/tools")["tools"]:
        if tool["risk_level"] != "READ_ONLY":
            continue
        schema, args = tool["parameters"], {}
        for name, field in schema.get("properties", {}).items():
            if "enum" in field and field["enum"]:
                args[name] = field["enum"][0]
            elif "default" in field:
                args[name] = field["default"]
        if tool["name"] == "port_check":
            option = schema.get("anyOf", [{}])[0].get("properties", {})
            args = {name: value["const"] for name, value in option.items()}
        for name, small in {"lines": 10, "limit": 3, "count": 1, "minutes": 1}.items():
            if name in args:
                args[name] = small
        if set(schema.get("required", [])) - set(args):
            results.append({"tool": tool["name"], "skipped": "No configured target"})
            continue
        try:
            result = request("/tools/" + tool["name"], args)
            results.append({"tool": tool["name"], "ok": result["ok"], "duration_ms": result.get("duration_ms"), "error": result.get("error")})
        except urllib.error.URLError as exc:
            results.append({"tool": tool["name"], "ok": False, "error_type": type(exc).__name__})
    print(json.dumps({"read_only_smoke": results}, indent=2))
    return 1 if any(item.get("ok") is False for item in results) else 0


if __name__ == "__main__":
    sys.exit(main())
