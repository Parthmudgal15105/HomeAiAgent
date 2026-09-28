from backend.app.routing import initial_diagnostic
from backend.app.schemas import IncidentSpec


def registry():
    def tool(name, properties, required=()):
        return {'name': name, 'risk_level': 'READ_ONLY', 'parameters': {
            'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False,
        }}
    return {
        'http_check': tool('http_check', {'url': {'enum': ['https://codeduel.online']}}, ('url',)),
        'disk_usage': tool('disk_usage', {}),
        'docker_inspect': tool('docker_inspect', {'container': {'enum': ['codeduel-api']}}, ('container',)),
        'docker_list': tool('docker_list', {}),
        'ping_host': tool('ping_host', {'hostname': {'enum': ['codeduel.online']}}, ('hostname',)),
    }


def route(category, target=''):
    return initial_diagnostic(IncidentSpec(category=category, target=target, symptom='test', confidence=.9), registry())


def test_http_service_routes_to_http_probe():
    assert route('http_service') == ('http_check', {'url': 'https://codeduel.online'})


def test_disk_routes_to_disk_usage():
    assert route('disk') == ('disk_usage', {})


def test_container_routes_to_schema_allowed_inspect():
    assert route('container', 'codeduel-api') == ('docker_inspect', {'container': 'codeduel-api'})


def test_container_with_unconfigured_target_uses_target_free_status():
    assert route('container', 'redis') == ('docker_list', {})


def test_network_routes_to_schema_allowed_network_probe():
    assert route('network') == ('ping_host', {'hostname': 'codeduel.online'})


def test_unknown_or_low_confidence_keeps_bounded_reasoning():
    assert initial_diagnostic(IncidentSpec(category='unknown', target='', symptom='test', confidence=.9), registry()) is None
    assert initial_diagnostic(IncidentSpec(category='disk', target='', symptom='test', confidence=.4), registry()) is None
