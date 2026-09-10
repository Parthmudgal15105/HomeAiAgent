"""Run on the host: uvicorn diagnostic_gateway.main:app --host 127.0.0.1 --port 18081."""
from __future__ import annotations

import hmac
import json
import logging
import os
import time
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from .config import GatewayConfig
from .safety import ApprovalError, ApprovalLedger, ToolError, redact
from .tools import DiagnosticTools

log = logging.getLogger("aiops.gateway")


def bounded_result(result: Any, max_bytes: int) -> Any:
    """Bound normalized Python diagnostics as well as subprocess output."""
    safe = redact(result)
    encoded = json.dumps(safe, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) <= max_bytes:
        return safe
    # Explicit truncation cannot accidentally look like a complete probe.
    return {"truncated": True, "output_limit_bytes": max_bytes,
            "original_bytes": len(encoded),
            "preview": encoded[:max_bytes // 2].decode("utf-8", errors="ignore")}


def create_app(config: GatewayConfig | None = None, *, token: str | None = None, approval_secret: str | None = None) -> FastAPI:
    config = config or GatewayConfig.from_env()
    token = token if token is not None else os.getenv("GATEWAY_TOKEN", "")
    approval_secret = approval_secret if approval_secret is not None else os.getenv("GATEWAY_APPROVAL_SECRET", "")
    registry = DiagnosticTools(config)
    ledger = ApprovalLedger(config.state_path) if config.writes_enabled else None
    application = FastAPI(title="AI Home Lab Diagnostic Gateway", version="1.0.0", docs_url=None, redoc_url=None, openapi_url=None)
    application.state.registry = registry

    def authenticate(authorization: str | None = Header(default=None)) -> None:
        if not token or len(token) < 32:
            raise HTTPException(status_code=503, detail="Gateway authentication is not configured")
        value = authorization or ""
        if not value.startswith("Bearer ") or not hmac.compare_digest(value[7:].encode(), token.encode()):
            raise HTTPException(status_code=401, detail="Gateway authentication required")

    @application.get("/healthz")
    def health() -> dict[str, Any]:
        return {"status": "ok" if len(token) >= 32 else "unconfigured", "service": "diagnostic_gateway"}

    @application.get("/tools", dependencies=[Depends(authenticate)])
    def tools() -> dict[str, Any]:
        return {"tools": registry.metadata()}

    @application.post("/tools/{name}", dependencies=[Depends(authenticate)])
    async def execute(name: str, request: Request, x_action_id: str = Header(default=""), x_approval_token: str = Header(default=""), x_approval_expires: str = Header(default="")) -> dict[str, Any]:
        started = time.monotonic()
        definition = registry.definitions.get(name)
        if definition is None:
            raise HTTPException(status_code=404, detail="Unknown or disabled tool")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 8192:
                raise HTTPException(status_code=413, detail="Tool arguments exceed size limit")
            body.extend(chunk)
        try:
            validated = definition.arguments.model_validate_json(bytes(body) or b"{}")
        except ValidationError as exc:
            # Pydantic's default errors include raw input; never echo that field.
            details = [{"field": ".".join(str(part) for part in err["loc"]), "type": err["type"]} for err in exc.errors()]
            raise HTTPException(status_code=422, detail=details) from exc
        arguments = validated.model_dump()
        approval_consumed = False
        try:
            registry.validate_scope(name, arguments)
            if definition.risk_level != "READ_ONLY":
                if ledger is None:
                    raise ApprovalError("Writes are disabled")
                # Sign exactly the submitted canonical args. Defaults validated
                # above do not mutate the signed payload (write schemas have none).
                ledger.consume(secret=approval_secret, action_id=x_action_id, tool=name, arguments=arguments, expires=x_approval_expires, signature=x_approval_token)
                approval_consumed = True
            result = await run_in_threadpool(definition.handler, **arguments)
            response = {"tool": name, "ok": True, "result": bounded_result(result, config.max_output_bytes), "duration_ms": round((time.monotonic() - started) * 1000)}
        except ApprovalError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ToolError as exc:
            response = {"tool": name, "ok": False, "result": {}, "error": str(redact(str(exc))), "duration_ms": round((time.monotonic() - started) * 1000)}
        except Exception as exc:
            log.error("tool=%s failure_type=%s", name, type(exc).__name__)
            response = {"tool": name, "ok": False, "result": {}, "error": "Diagnostic failed; inspect the gateway service state", "duration_ms": round((time.monotonic() - started) * 1000)}
        if approval_consumed and ledger:
            ledger.complete(x_action_id, response)
        log.info("tool=%s ok=%s duration_ms=%s", name, response["ok"], response["duration_ms"])
        return response

    return application


app = create_app()
