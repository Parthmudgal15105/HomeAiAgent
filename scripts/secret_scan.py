#!/usr/bin/env python3
"""Fail closed on credential files and common secret literals; never print values.

By default scan the Git index plus nonignored new files. --tracked scans only
tracked working-tree files; --staged scans the exact staged blob contents before
a commit. This is a local, dependency-free guard, not a guarantee that arbitrary
unknown credential formats can be recognized. Intentional test literals require
an explicit `secret-scan: fixture` comment on the same line.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess


PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "provider-token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}|tskey-(?:auth|api|client|oauth)-[A-Za-z0-9_-]{12,}|AKIA[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{35}|AQ\.[A-Za-z0-9_-]{40,})\b"),
    "credential-uri": re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/:@\"']+:[^\s/@\"']+@"),
    "secret-assignment": re.compile(r'''(?i)\b(?:[A-Z_]*(?:PASSWORD|API_KEY|API_TOKEN|AUTH_TOKEN|APPROVAL_SECRET|SESSION_SECRET|PRIVATE_KEY))["']?\s*[:=]\s*["']?([A-Za-z0-9_+/.=-]{24,})'''),
}
PLACEHOLDERS = {"replace", "replace_me", "changeme", "example", "placeholder"}


def scan_text(path: str, content: str) -> list[dict]:
    findings = []
    name = Path(path).name
    parts = Path(path).parts
    if (name == ".env" or (name.startswith(".env.") and name != ".env.example")
            or name == ".local-access.txt" or name in {"id_rsa", "id_ed25519"}
            or "data" in parts or "backups" in parts
            or name.endswith((".sqlite", ".sqlite3", ".db", ".log"))):
        findings.append({"path": path, "line": 0, "rule": "private-runtime-file"})
    for number, line in enumerate(content.splitlines(), 1):
        if "secret-scan: fixture" in line:
            continue
        for rule, pattern in PATTERNS.items():
            for match in pattern.finditer(line):
                if rule == "credential-uri":
                    password = match.group().split("://", 1)[1].split(":", 1)[1][:-1].lower()
                    if password in PLACEHOLDERS or password.startswith("${"):
                        continue
                findings.append({"path": path, "line": number, "rule": rule})
                break
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--tracked", action="store_true")
    modes.add_argument("--staged", action="store_true")
    args = parser.parse_args()
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    command = ["git", "ls-files", "-z", "--cached"]
    if not (args.tracked or args.staged):
        command.extend(["--others", "--exclude-standard"])
    files = sorted(set(subprocess.check_output(command, cwd=root).decode().split("\0")) - {""})
    findings, checked = [], 0
    for filename in files:
        path = root / filename
        if args.staged:
            raw = subprocess.check_output(["git", "show", ":" + filename], cwd=root)
        elif path.is_symlink():
            findings.append({"path": filename, "line": 0, "rule": "unreviewed-symlink"})
            continue
        elif not path.is_file():
            continue  # A staged deletion has no payload to scan.
        else:
            raw = path.read_bytes()
        if len(raw) > 10_000_000:
            findings.append({"path": filename, "line": 0, "rule": "oversized-source-file"})
            continue
        findings.extend(scan_text(filename, raw.decode("utf-8", errors="replace")))
        checked += 1
    print(json.dumps({"files_scanned": checked, "findings": findings, "passed": not findings}, indent=2))
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
