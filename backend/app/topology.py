"""Administrator-owned service definitions; metadata never grants tool access."""
import json
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .schemas import CheckSpec

Identifier = Annotated[str, Field(pattern=r'^[a-zA-Z0-9_.-]+$', max_length=100)]


class ServiceProfile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(default='', max_length=150)
    type: str = Field(default='service', max_length=80)
    description: str = Field(default='', max_length=3000)
    public_urls: list[str] = Field(default_factory=list, max_length=10)
    local_health_urls: list[str] = Field(default_factory=list, max_length=10)
    containers: list[Identifier] = Field(default_factory=list, max_length=50)
    systemd_services: list[Identifier] = Field(default_factory=list, max_length=20)
    depends_on: list[Identifier] = Field(default_factory=list, max_length=30)
    tags: list[str] = Field(default_factory=list, max_length=30)
    health_checks: list[CheckSpec] = Field(default_factory=list, max_length=30)
    overview: bool = False
    host: str | None = Field(default=None, max_length=253)
    port: int | None = Field(default=None, ge=1, le=65535)

    @model_validator(mode='before')
    @classmethod
    def normalize_legacy_profile(cls, value):
        value = dict(value)
        for singular, plural in (('container', 'containers'), ('systemd_service', 'systemd_services')):
            if singular in value:
                value[plural] = list(dict.fromkeys([*value.get(plural, []), value.pop(singular)]))
        if 'url' in value:
            url = value.pop('url')
            key = 'public_urls' if url.startswith('https://') else 'local_health_urls'
            value[key] = list(dict.fromkeys([*value.get(key, []), url]))
        return value


class Topology(BaseModel):
    model_config = ConfigDict(extra='allow')
    services: dict[Identifier, ServiceProfile] = Field(default_factory=dict, max_length=100)

    @model_validator(mode='after')
    def references_exist(self):
        for key, profile in self.services.items():
            unknown = set(profile.depends_on) - self.services.keys()
            if unknown:
                raise ValueError(f'Service {key} has undefined dependencies: {sorted(unknown)}')
            profile.name = profile.name or key
        return self


def load_topology(path: str) -> dict:
    target = Path(path)
    if not target.is_file():
        return {'services': {}, 'notice': 'Topology has not been configured.'}
    if target.stat().st_size > 200_000:
        raise ValueError('Topology exceeds the 200KB configuration limit')
    return Topology.model_validate(json.loads(target.read_text())).model_dump(exclude_defaults=True)
