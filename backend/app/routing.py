"""Deterministic first diagnostics derived only from the gateway registry."""
from .schemas import IncidentSpec


ROUTES = {
    'http_service': ('http_check',),
    'container': ('docker_inspect', 'docker_list'),
    'process': ('find_process', 'process_list'),
    'systemd_service': ('service_status', 'journal_logs'),
    'network': ('ping_host', 'dns_lookup', 'network_interfaces'),
    'disk': ('disk_usage',),
    'database': ('mongodb_atlas_connectivity', 'port_check', 'dns_lookup'),
}


def constrained_arguments(tool: dict, target: str = '') -> dict | None:
    """Choose only defaults/enums already granted by the gateway schema."""
    schema = tool.get('parameters', {})
    properties = schema.get('properties', {})
    values = {}
    for key in schema.get('required', []):
        prop = properties.get(key, {})
        allowed = prop.get('enum', [])
        if key in ('container', 'service', 'hostname', 'host', 'process') and target in allowed:
            values[key] = target
        elif 'const' in prop:
            values[key] = prop['const']
        elif allowed:
            values[key] = allowed[0]
        elif 'default' in prop:
            values[key] = prop['default']
        else:
            return None
    return values


def initial_diagnostic(spec: IncidentSpec, registry: dict[str, dict]) -> tuple[str, dict] | None:
    """Return one read-only, schema-valid diagnostic or leave reasoning bounded."""
    if spec.category == 'unknown' or spec.confidence < .5:
        return None
    for name in ROUTES.get(spec.category, ()):
        tool = registry.get(name)
        if not tool or tool.get('risk_level') != 'READ_ONLY':
            continue
        arguments = constrained_arguments(tool, spec.target)
        if arguments is not None:
            return name, arguments
    return None
