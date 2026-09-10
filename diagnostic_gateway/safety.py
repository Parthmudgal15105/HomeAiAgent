"""Execution limits, redaction, URL address pinning and signed one-use approvals."""
from __future__ import annotations

import hashlib
import hmac
import http.client
import ipaddress
import io
import json
import os
import re
import selectors
import shutil
import signal
import socket
import sqlite3
import ssl
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import dns.exception
import dns.resolver


class ToolError(Exception):
    """Expected safe diagnostic failure; no traceback is sent to the model."""


class ApprovalError(ToolError):
    pass


SECRET_KEYS = re.compile(r"(?i)(?:password|passwd|secret|token|authorization|api[_-]?key|credential|private[_-]?key|cookie|session[_-]?(?:id|key)?)")
URL_CREDS = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^\s/@]+(?::[^\s/@]*)?@")
KEY_VALUE = re.compile(r"(?i)((?:password|passwd|secret|[\w-]*token|authorization|api[_-]?key|cookie|session[_-]?(?:id|key)?|mongodb_uri|mongo_uri|database_url|redis_url)[\"']?\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)")
BEARER = re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9_+/=.:-]+")
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
CLI_SECRET = re.compile(r"(?i)((?:--?)(?:token|password|passwd|secret|api[_-]?key|client[_-]?secret|credentials)(?:=|\s+))(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)")
RAW_KEYS = re.compile(r"\b(?:tskey-(?:auth|api|client|oauth)-[A-Za-z0-9_-]{8,}|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b")
# Cloudflare tunnel credentials are a long base64 JSON object (not a JWT).
# Redact such blobs when they appear without a key/flag as well.
BASE64_JSON = re.compile(r"\beyJ[A-Za-z0-9_+/=-]{24,}")
PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z ]*)PRIVATE KEY-----.*?-----END (?:[A-Z ]*)PRIVATE KEY-----", re.DOTALL)
# Cookie headers may contain many semicolon-separated secrets, not just one.
SENSITIVE_HEADER = re.compile(r"(?im)(\b(?:set-cookie|cookie|authorization|proxy-authorization)\s*:\s*)[^\r\n]+")
DATABASE_URI = re.compile(r"(?i)\b(?:mongodb(?:\+srv)?|postgres(?:ql)?(?:\+psycopg)?|redis(?:s)?)://[^\s<>\"']+")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if SECRET_KEYS.search(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    value = PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", value)
    value = SENSITIVE_HEADER.sub(r"\1[REDACTED HEADER]", value)
    value = DATABASE_URI.sub("[REDACTED DATABASE URI]", value)
    value = URL_CREDS.sub(r"\1[REDACTED]@", value)
    value = BEARER.sub(r"\1 [REDACTED]", value)
    value = CLI_SECRET.sub(r"\1[REDACTED]", value)
    value = KEY_VALUE.sub(r"\1[REDACTED]", value)
    value = JWT.sub("[REDACTED JWT]", value)
    value = RAW_KEYS.sub("[REDACTED KEY]", value)
    value = BASE64_JSON.sub("[REDACTED ENCODED CREDENTIAL]", value)
    # Terminal control sequences must not reach a browser or terminal.
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int
    truncated: bool = False


COMMANDS = frozenset({"docker", "systemctl", "journalctl", "ip", "ping", "tailscale"})


def run_command(argv: list[str], *, timeout: float = 8, max_bytes: int = 32768, check: bool = True) -> CommandResult:
    """Bound memory while reading both pipes; kill the whole child group on expiry."""
    if not argv or argv[0] not in COMMANDS or any("\x00" in item for item in argv):
        raise ToolError("Command is not allowlisted")
    binary = shutil.which(argv[0], path="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
    if not binary:
        raise ToolError(f"Required host executable is unavailable: {argv[0]}")
    env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "HOME": "/nonexistent"}
    process = subprocess.Popen([binary, *argv[1:]], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, env=env, start_new_session=True)
    buffers: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    selector = selectors.DefaultSelector()
    assert process.stdout and process.stderr
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    deadline, size, truncated = time.monotonic() + timeout, 0, False
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ToolError(f"Host command exceeded {timeout:g} second timeout")
            for key, _ in selector.select(min(remaining, 0.1)):
                chunk = os.read(key.fileobj.fileno(), min(4096, max_bytes - size + 1))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                room = max_bytes - size
                buffers[key.data].extend(chunk[:room])
                size += min(len(chunk), room)
                if len(chunk) > room:
                    truncated = True
                    os.killpg(process.pid, signal.SIGKILL)
                    for item in list(selector.get_map().values()):
                        selector.unregister(item.fileobj)
                    break
        process.wait(timeout=max(0.1, deadline - time.monotonic()))
    except subprocess.TimeoutExpired as exc:
        raise ToolError("Host command timed out") from exc
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
        selector.close()
        process.stdout.close()
        process.stderr.close()
    result = CommandResult(buffers["stdout"].decode("utf-8", errors="replace"), buffers["stderr"].decode("utf-8", errors="replace"), process.returncode, truncated)
    if check and result.returncode != 0 and not truncated:
        raise ToolError(str(redact(result.stderr[:2000] or "Host command failed")))
    return result


def resolve_addresses(host: str, lifetime: float = 3.0) -> list[str]:
    try:
        return [str(ipaddress.ip_address(host))]
    except ValueError:
        pass
    if host == "localhost":
        return ["127.0.0.1", "::1"]
    resolver = dns.resolver.Resolver()
    resolver.lifetime = lifetime
    deadline = time.monotonic() + lifetime
    addresses = []
    for record in ("A", "AAAA"):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            addresses.extend(str(answer) for answer in resolver.resolve(host, record, lifetime=remaining))
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout):
            continue
    if not addresses:
        raise ToolError(f"No A/AAAA addresses resolved for {host}")
    return sorted(set(addresses))[:16]


def safe_address(address: str, *, local_target: bool = False, container_target: bool = False) -> bool:
    ip = ipaddress.ip_address(address)
    if local_target:
        return ip.is_loopback
    if ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return False
    if container_target:
        return ip.is_private and not ip.is_loopback
    return ip.is_global


class DeadlineSocket:
    """Make HTTP header/body reads obey one wall-clock deadline, including TLS."""
    def __init__(self, sock: socket.socket, deadline: float) -> None:
        self.sock, self.deadline = sock, deadline
        self.io_refs = 0
        self.close_requested = False

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("HTTP request exceeded total time limit")
        self.sock.settimeout(remaining)
        return remaining

    def recv_into(self, buffer: Any, nbytes: int = 0, flags: int = 0) -> int:
        self.remaining()
        return self.sock.recv_into(buffer, nbytes, flags)

    def sendall(self, data: bytes, flags: int = 0) -> None:
        self.remaining()
        self.sock.sendall(data, flags)

    def makefile(self, mode: str, buffering: int | None = None) -> Any:
        if mode != "rb":
            raise ValueError("Unsupported HTTP socket mode")
        self.io_refs += 1
        return io.BufferedReader(socket.SocketIO(self, "r"))

    def _decref_socketios(self) -> None:
        self.io_refs -= 1
        if self.close_requested and self.io_refs <= 0:
            self.sock.close()

    def close(self) -> None:
        self.close_requested = True
        if self.io_refs <= 0:
            self.sock.close()


class PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, hostname: str, address: str, port: int, timeout: float, secure: bool) -> None:
        super().__init__(hostname, port=port, timeout=timeout)
        self.address, self.secure = address, secure
        self.deadline = time.monotonic() + timeout

    def connect(self) -> None:
        # The literal numeric address goes straight into the socket. No second DNS
        # lookup is possible between validation and connection (DNS rebinding).
        ip = ipaddress.ip_address(self.address)
        sock = socket.socket(socket.AF_INET6 if ip.version == 6 else socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.address, self.port))
            if self.secure:
                sock.settimeout(max(0.01, self.deadline - time.monotonic()))
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
            self.sock = DeadlineSocket(sock, self.deadline)
        except Exception:
            sock.close()
            raise


def http_probe(url: str, *, address: str | None = None, container_target: bool = False, timeout: float = 5.0) -> dict[str, Any]:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        local_target = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local_target = host == "localhost"
    addresses = [address] if address else resolve_addresses(host)
    # Reject the complete DNS answer on mixed private/public answers.
    if not all(safe_address(ip, local_target=local_target, container_target=container_target) for ip in addresses):
        raise ToolError("HTTP destination address is outside the allowed network scope")
    start = time.monotonic()
    connection = PinnedHTTPConnection(host, addresses[0], port, timeout, parsed.scheme == "https")
    response = None
    try:
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        connection.request("GET", path, headers={"User-Agent": "AIHomeLabDiagnosticGateway/1.0", "Accept": "application/json,text/plain,text/html;q=0.5", "Connection": "close"})
        response = connection.getresponse()
        # One bounded socket read prevents slow-drip bodies extending indefinitely.
        body = response.read1(4097)
        return {"url": url, "reachable": True, "status_code": response.status, "healthy": 200 <= response.status < 400, "latency_ms": round((time.monotonic() - start) * 1000), "body_preview": body[:4096].decode("utf-8", errors="replace"), "body_truncated": len(body) > 4096, "redirect_followed": False, "resolved_address": addresses[0]}
    except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
        return {"url": url, "reachable": False, "healthy": False, "latency_ms": round((time.monotonic() - start) * 1000), "error": str(redact(str(exc)))[:500], "resolved_address": addresses[0]}
    finally:
        if response is not None:
            response.close()
        connection.close()


def canonical_arguments(arguments: dict[str, Any]) -> str:
    return json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def approval_signature(secret: str, action_id: str, tool: str, arguments: dict[str, Any], expires: str) -> str:
    message = f"{action_id}:{tool}:{canonical_arguments(arguments)}:{expires}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


class ApprovalLedger:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute("CREATE TABLE IF NOT EXISTS consumed_approvals (action_id TEXT PRIMARY KEY, tool TEXT NOT NULL, consumed_at REAL NOT NULL, result TEXT)")
        os.chmod(path, 0o600)

    def consume(self, *, secret: str, action_id: str, tool: str, arguments: dict[str, Any], expires: str, signature: str) -> None:
        if len(secret) < 32 or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", action_id):
            raise ApprovalError("Write approval is not valid")
        try:
            expiry = int(expires)
        except (TypeError, ValueError) as exc:
            raise ApprovalError("Write approval expiry is required") from exc
        now = time.time()
        if expiry <= now or expiry > now + 600:
            raise ApprovalError("Write approval is expired or outside its permitted lifetime")
        expected = approval_signature(secret, action_id, tool, arguments, expires)
        if not hmac.compare_digest(signature.encode(), expected.encode()):
            raise ApprovalError("Write approval signature does not match action")
        try:
            with sqlite3.connect(self.path, timeout=5) as db:
                db.execute("INSERT INTO consumed_approvals(action_id,tool,consumed_at) VALUES(?,?,?)", (action_id, tool, now))
        except sqlite3.IntegrityError as exc:
            raise ApprovalError("This approval has already been consumed") from exc

    def complete(self, action_id: str, result: dict[str, Any]) -> None:
        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute("UPDATE consumed_approvals SET result=? WHERE action_id=?", (json.dumps(redact(result), separators=(",", ":"))[:32768], action_id))
