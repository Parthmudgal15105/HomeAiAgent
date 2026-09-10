"""Only administrator-owned configuration determines infrastructure scope."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContainerHTTP(BaseModel):
    model_config = ConfigDict(extra="forbid")
    container: str
    port: int = Field(ge=1, le=65535)
    path: str = "/"
    network: str | None = None

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//") or any(c in value for c in "\r\n"):
            raise ValueError("HTTP path must be a relative absolute path")
        return value


class TCPAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str
    port: int = Field(ge=1, le=65535)


class GatewayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    containers: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=lambda: ["docker", "cloudflared", "tailscaled", "ssh"])
    hosts: list[str] = Field(default_factory=lambda: ["codeduel.online", "localhost", "127.0.0.1"])
    http_urls: list[str] = Field(default_factory=lambda: ["https://codeduel.online", "http://127.0.0.1:8085"])
    container_http: dict[str, ContainerHTTP] = Field(default_factory=dict)
    tcp_targets: list[TCPAddress] = Field(default_factory=list)
    disk_paths: list[str] = Field(default_factory=lambda: ["/"])
    write_containers: list[str] = Field(default_factory=list)
    write_services: list[str] = Field(default_factory=list)
    writes_enabled: bool = False
    command_timeout_seconds: int = Field(default=8, ge=1, le=30)
    max_output_bytes: int = Field(default=32768, ge=1024, le=131072)
    state_path: str = "/var/lib/aiops-gateway/approvals.sqlite3"

    @model_validator(mode="after")
    def validate_scopes(self) -> "GatewayConfig":
        import re
        from urllib.parse import urlsplit
        identifier = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
        for name in self.containers + self.services + self.write_containers + self.write_services:
            if not identifier.fullmatch(name):
                raise ValueError("Unsafe container or service identifier")
        for host in self.hosts + [target.host for target in self.tcp_targets]:
            if not host or len(host) > 253 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-:" for c in host):
                raise ValueError("Unsafe configured host")
        if not set(self.write_containers).issubset(self.containers) or not set(self.write_services).issubset(self.services):
            raise ValueError("Write targets must be included in the diagnostic allowlist")
        for endpoint in self.container_http.values():
            if endpoint.container not in self.containers:
                raise ValueError("Container HTTP target must be allowlisted")
        for url in self.http_urls:
            parsed = urlsplit(url)
            _ = parsed.port  # Validate the port format/range at startup.
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or any(ord(c) < 32 for c in url):
                raise ValueError("Configured HTTP URL is unsafe")
            if parsed.hostname not in self.hosts:
                raise ValueError("HTTP hosts must be included in hosts allowlist")
        if any(not p.startswith("/") for p in self.disk_paths):
            raise ValueError("Disk paths must be absolute")
        return self

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        path = os.getenv("GATEWAY_CONFIG_PATH")
        payload: dict[str, Any] = json.loads(Path(path).read_text()) if path else {}
        if os.getenv("GATEWAY_STATE_PATH"):
            payload["state_path"] = os.environ["GATEWAY_STATE_PATH"]
        return cls.model_validate(payload)


# Boundary values are deliberate: 80–<90 warning; 90–95 high; >95 critical.
def utilization_severity(percent: float) -> str:
    if percent > 95:
        return "critical"
    if percent >= 90:
        return "high"
    if percent >= 80:
        return "warning"
    return "normal"
