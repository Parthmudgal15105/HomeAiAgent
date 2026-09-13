import re
from typing import Any


SECRET_KEY = re.compile(r'(password|passwd|secret|token|api[_-]?key|authorization|cookie|credential|private[_-]?key|session[_-]?(?:id|key))', re.I)
PATTERNS = [
    (re.compile(r"(?im)(\b(?:set-cookie|cookie|authorization|proxy-authorization)\s*:\s*)[^\r\n]+"), r'\1[REDACTED HEADER]'),
    (re.compile(r"(?i)\b(?:mongodb(?:\+srv)?|postgres(?:ql)?(?:\+psycopg)?|redis(?:s)?)://[^\s<>\"']+"), '[REDACTED DATABASE URI]'),
    (re.compile(r'(?i)((?:Bearer|Basic)\s+)[A-Za-z0-9._~+/=:-]+'), r'\1[REDACTED]'),
    (re.compile(r'''(?i)((?:--?)(?:token|password|passwd|secret|api[_-]?key|client[_-]?secret|credentials)(?:=|\s+))(?:"[^"]*"|'[^']*'|[^\s,;]+)'''), r'\1[REDACTED]'),
    (re.compile(r'tskey-[a-z]+-[A-Za-z0-9_-]+'), '[REDACTED TAILSCALE KEY]'),
    (re.compile(r'(?i)([a-z][a-z0-9+.-]*://)[^\s/@]+(?::[^\s/@]*)?@'), r'\1[REDACTED]@'),
    (re.compile(r'''(?i)((?:password|passwd|secret|[\w-]*token|authorization|api[_-]?key|cookie|session[_-]?(?:id|key)?|mongodb_uri|mongo_uri|database_url|redis_url)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)'''), r'\1[REDACTED]'),
    (re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b'), '[REDACTED JWT]'),
    (re.compile(r'\b(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{35}|AQ\.[A-Za-z0-9_-]{40,})\b'), '[REDACTED KEY]'),
    (re.compile(r'\beyJ[A-Za-z0-9_+/=-]{24,}'), '[REDACTED ENCODED CREDENTIAL]'),
    (re.compile(r'-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----'), '[REDACTED PRIVATE KEY]'),
]


def redact(value: Any, max_string: int = 16000) -> Any:
    if isinstance(value, dict):
        return {str(k): '[REDACTED]' if SECRET_KEY.search(str(k)) else redact(v, max_string) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, max_string) for v in value[:500]]
    if isinstance(value, str):
        for pattern, replacement in PATTERNS:
            value = pattern.sub(replacement, value)
        value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', value)
        return value[:max_string] + ('…[truncated]' if len(value) > max_string else '')
    return value


def disk_severity(percent: float, warning: float = 80, high: float = 90, critical: float = 95) -> str:
    if percent > critical:
        return 'critical'
    if percent >= high:
        return 'high'
    if percent >= warning:
        return 'warning'
    return 'normal'


def evidence_confidence(observations: list, proposed: float, contradictions: list | None = None) -> tuple[float, dict]:
    """Evidence-based ceiling, not a calibrated probability or semantic proof.

    Independent means distinct diagnostic families, not repeated logs or IDs.
    A model's low confidence is preserved; historical retrieval contributes zero.
    """
    groups = {'docker_list': 'container_state', 'docker_inspect': 'container_state',
              'docker_logs': 'logs', 'journal_logs': 'logs',
              'service_status': 'service_state', 'cloudflared_status': 'service_state',
              'http_check': 'http', 'port_check': 'tcp', 'ping_host': 'network_probe',
              'network_interfaces': 'interfaces', 'route_table': 'routes'}
    successful = [item for item in observations if item.raw_result.get('ok') is True]
    families = {groups.get(item.tool_name, item.tool_name) for item in successful}
    direct_failure = any(item.tool_name in ('docker_logs', 'journal_logs') and re.search(
        r'ECONNREFUSED|ENOSPC|no space left|rf.?kill|connection (?:refused|failed)|out of memory|fatal|serverselectionerror',
        str(item.normalized_result), re.I) for item in successful)
    ceiling = min(.85, .25 + .15 * len(families)) if families else .15
    if direct_failure:
        ceiling = min(.95, ceiling + .1)
    conflicts = len(set(contradictions or []))
    if conflicts:
        ceiling = max(.15, ceiling - min(.4, .2 * conflicts))
    if len(successful) < len(observations):
        ceiling = max(.15, ceiling - .1)
    note = {'method': 'Evidence-family ceiling v1; not an empirically calibrated probability',
            'independent_diagnostic_families': sorted(families), 'direct_failure_log': direct_failure,
            'contradicting_observations': conflicts, 'historical_context_weight': 0,
            'ceiling': round(ceiling, 2),
            'limitations': 'Citation ownership and execution are checked; causal agreement and unresolved layers still require model/operator interpretation.'}
    return round(min(proposed, ceiling), 3), note
