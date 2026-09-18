import hashlib
import hmac
import json
import time

import httpx
from jsonschema import Draft202012Validator

from .config import Settings
from .safety import redact


READ_TOOLS = frozenset({'dns_lookup', 'ping_host', 'http_check', 'docker_list', 'docker_inspect', 'docker_logs', 'service_status', 'is_service_enabled', 'journal_logs', 'network_interfaces', 'route_table', 'default_gateway', 'cpu_usage', 'memory_usage', 'disk_usage', 'filesystem_mounts', 'temperatures', 'system_uptime', 'process_list', 'find_process', 'inspect_process', 'listening_ports', 'port_check', 'tailscale_status', 'cloudflared_status', 'docker_stats', 'recent_docker_events', 'check_application_health'})
WRITE_TOOLS = frozenset({'restart_container', 'start_container', 'stop_container', 'restart_service', 'start_service', 'stop_service'})


def validate_tool(registry: dict, tool: str, arguments: dict, allow_write: bool = False) -> dict:
    if tool not in READ_TOOLS | WRITE_TOOLS or tool not in registry:
        raise ValueError('Tool is not in the explicit backend allowlist')
    metadata = registry[tool]
    risk = metadata.get('risk_level')
    if tool in WRITE_TOOLS:
        if not allow_write or risk != 'LOW_RISK_WRITE':
            raise ValueError('Write tools require a persisted authorized action')
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
            if not approval or approval.get('approval_status') not in ('APPROVED', 'AUTO_AUTHORIZED') or not self.settings.gateway_approval_secret:
                raise ValueError('Authorized action and configured signing secret required')
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


class OperationsGateway:
    """Expose one topology-backed composite read alongside the host gateway tools."""

    def __init__(self, settings: Settings, host_gateway):
        self.settings, self.host_gateway = settings, host_gateway

    async def registry(self) -> dict:
        from .application_health import application_names
        registry = dict(await self.host_gateway.registry())
        names = application_names(self.settings.topology())
        if names:
            registry['check_application_health'] = {
                'name': 'check_application_health',
                'description': 'Run administrator-configured read-only health checks for an application and its dependencies.',
                'risk_level': 'READ_ONLY',
                'parameters': {'type': 'object', 'properties': {'application': {'type': 'string', 'enum': names}},
                               'required': ['application'], 'additionalProperties': False},
            }
        return registry

    async def execute(self, tool: str, arguments: dict, approval: dict | None = None) -> dict:
        if tool != 'check_application_health':
            return await self.host_gateway.execute(tool, arguments, approval=approval)
        if approval is not None:
            raise ValueError('Application health is read-only')
        validate_tool(await self.registry(), tool, arguments)
        from .application_health import check_application_health
        result = await check_application_health(self.settings, self.host_gateway, arguments['application'])
        return {'tool': tool, 'ok': True, 'result': redact(result), 'duration_ms': 0}
