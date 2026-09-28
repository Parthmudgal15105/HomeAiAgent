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


class AtlasSeed(BaseModel):
    """One administrator-approved Atlas SRV seed and its shard DNS boundary."""

    model_config = ConfigDict(extra="forbid")
    seed: str = Field(min_length=1, max_length=253)
    # Atlas SRV answers must stay under this exact DNS suffix.  It is not a
    # wildcard and deliberately excludes arbitrary targets returned by DNS.
    shard_hostname_suffix: str = Field(min_length=3, max_length=253)
    # Atlas clients use this fixed MongoDB TLS port.  Do not let SRV data select
    # an arbitrary service port on an otherwise permitted hostname.
    port: int = Field(default=27017, ge=27017, le=27017)

    @field_validator("seed", "shard_hostname_suffix")
    @classmethod
    def safe_dns_name(cls, value: str) -> str:
        import re

        normalized = value.lower().rstrip(".")
        label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
        if (not normalized or len(normalized) > 253 or not re.fullmatch(rf"{label}(?:\.{label})+", normalized)):
            raise ValueError("Atlas seed and shard suffix must be DNS hostnames")
        return normalized

    @model_validator(mode="after")
    def validate_seed_boundary(self) -> "AtlasSeed":
        if self.seed == self.shard_hostname_suffix or not self.seed.endswith("." + self.shard_hostname_suffix):
            raise ValueError("Atlas seed must be below its configured shard hostname suffix")
        return self


class GatewayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    containers: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=lambda: ["docker", "cloudflared", "tailscaled", "ssh"])
    hosts: list[str] = Field(default_factory=lambda: ["codeduel.online", "localhost", "127.0.0.1"])
    http_urls: list[str] = Field(default_factory=lambda: ["https://codeduel.online", "http://127.0.0.1:8085"])
    container_http: dict[str, ContainerHTTP] = Field(default_factory=dict)
    tcp_targets: list[TCPAddress] = Field(default_factory=list)
    # This is intentionally separate from generic host/TCP allowlists: an Atlas
    # diagnostic begins only from one named SRV seed and cannot accept a URI.
    atlas_seeds: list[AtlasSeed] = Field(default_factory=list)
    disk_paths: list[str] = Field(default_factory=lambda: ["/"])
    write_containers: list[str] = Field(default_factory=list)
    write_services: list[str] = Field(default_factory=list)
    # Exact tool names per target. Missing entries deny writes.
    allowed_actions: dict[str, list[str]] = Field(default_factory=dict)
    autonomous_actions: dict[str, list[str]] = Field(default_factory=dict)
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
        if len({seed.seed for seed in self.atlas_seeds}) != len(self.atlas_seeds):
            raise ValueError("Atlas seed allowlist entries must be unique")
        if not set(self.write_containers).issubset(self.containers) or not set(self.write_services).issubset(self.services):
            raise ValueError("Write targets must be included in the diagnostic allowlist")
        valid = {"start_container", "restart_container", "stop_container", "start_service", "restart_service", "stop_service"}
        for target, actions in self.allowed_actions.items():
            if target not in self.write_containers + self.write_services or not actions or len(actions) != len(set(actions)):
                raise ValueError("Action policy target must be a unique configured write target")
            category = "_container" if target in self.write_containers else "_service"
            if any(action not in valid or not action.endswith(category) for action in actions):
                raise ValueError("Action policy contains an invalid tool for its target")
            if target in {"docker", "ssh", "sshd", "tailscaled"} or (target == "cloudflared" and "stop_service" in actions):
                raise ValueError("Action policy grants a protected host operation")
        for target, actions in self.autonomous_actions.items():
            if not actions or not set(actions).issubset(self.allowed_actions.get(target, [])) or any(action.startswith("stop_") for action in actions):
                raise ValueError("Autonomous action must be an allowed start or restart")
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
