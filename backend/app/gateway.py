import hashlib
import hmac
import json
import time

import httpx
from jsonschema import Draft202012Validator

from .config import Settings
from .safety import redact


READ_TOOLS = frozenset({'dns_lookup', 'ping_host', 'http_check', 'docker_list', 'docker_inspect', 'docker_logs', 'service_status', 'journal_logs', 'network_interfaces', 'route_table', 'memory_usage', 'disk_usage', 'system_uptime', 'process_list', 'port_check', 'tailscale_status', 'cloudflared_status', 'docker_stats', 'recent_docker_events'})
WRITE_TOOLS = frozenset({'restart_container', 'start_container', 'restart_service'})


def validate_tool(registry: dict, tool: str, arguments: dict, allow_write: bool = False) -> dict:
    if tool not in READ_TOOLS | WRITE_TOOLS or tool not in registry:
        raise ValueError('Tool is not in the explicit backend allowlist')
    metadata = registry[tool]
    risk = metadata.get('risk_level')
    if tool in WRITE_TOOLS:
        if not allow_write or risk != 'LOW_RISK_WRITE':
            raise ValueError('Write tools require persisted user approval')
    elif risk != 'READ_ONLY':
        raise ValueError('Tool risk does not match backend policy')
    schema = metadata.get('parameters', {})
    if not schema or schema.get('type') != 'object':
        raise ValueError('Tool has no valid argument schema')
    Draft202012Validator(schema).validate(arguments)
    return metadata


class DiagnosticGateway:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._registry: dict | None = None

    async def registry(self) -> dict:
        if self._registry is None:
            async with httpx.AsyncClient(timeout=self.settings.agent_tool_timeout_seconds, trust_env=False) as client:
                response = await client.get(self.settings.gateway_url.rstrip('/') + '/tools', headers={'Authorization': f'Bearer {self.settings.gateway_token}'})
                response.raise_for_status()
                body = response.json()
            entries = body['tools'] if isinstance(body, dict) else body
            self._registry = {entry['name']: entry for entry in entries}
        return self._registry

    async def execute(self, tool: str, arguments: dict, approval: dict | None = None) -> dict:
        registry = await self.registry()
        validate_tool(registry, tool, arguments, allow_write=approval is not None)
        headers = {'Authorization': f'Bearer {self.settings.gateway_token}'}
        if tool in WRITE_TOOLS:
            if not approval or approval.get('approval_status') != 'APPROVED' or not self.settings.gateway_approval_secret:
                raise ValueError('Approved action and configured signing secret required')
            action_id = approval['id']
            expires = str(int(time.time()) + 120)
            canonical = json.dumps(arguments, sort_keys=True, separators=(',', ':'))
            message = f'{action_id}:{tool}:{canonical}:{expires}'
            signature = hmac.new(self.settings.gateway_approval_secret.encode(), message.encode(), hashlib.sha256).hexdigest()
            headers.update({'X-Action-ID': action_id, 'X-Approval-Expires': expires, 'X-Approval-Token': signature})
        timeout = self.settings.agent_write_timeout_seconds if tool in WRITE_TOOLS else self.settings.agent_tool_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            response = await client.post(self.settings.gateway_url.rstrip('/') + f'/tools/{tool}', json=arguments, headers=headers)
            response.raise_for_status()
            if len(response.content) > 262144:
                raise ValueError('Gateway response exceeds size limit')
            return redact(response.json())
