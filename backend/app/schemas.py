from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class IncidentCreate(StrictModel):
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(default='', max_length=10000)
    service: str = Field(default='codeduel', max_length=100, pattern=r'^[a-zA-Z0-9_.-]+$')
    severity: Literal['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] = 'MEDIUM'


class HypothesisUpdate(StrictModel):
    description: str = Field(min_length=3, max_length=1000)
    confidence: float = Field(ge=0, le=1)
    status: Literal['ACTIVE', 'SUPPORTED', 'ELIMINATED', 'CONFIRMED'] = 'ACTIVE'
    supporting_observation_ids: list[str] = Field(default_factory=list, max_length=30)
    contradicting_observation_ids: list[str] = Field(default_factory=list, max_length=30)


class Remediation(StrictModel):
    tool: str = Field(max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=3, max_length=1500)


class Decision(StrictModel):
    decision_type: Literal['TOOL_CALL', 'DIAGNOSIS', 'REQUEST_APPROVAL', 'NEED_USER_INPUT', 'STOP']
    tool: str | None = Field(default=None, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default='', max_length=1500)
    hypothesis_updates: list[HypothesisUpdate] = Field(default_factory=list, max_length=12)
    root_cause: str | None = Field(default=None, max_length=3000)
    confidence: float = Field(default=0, ge=0, le=1)
    evidence_observation_ids: list[str] = Field(default_factory=list, max_length=30)
    summary: str = Field(default='', max_length=4000)
    remediation: list[Remediation] = Field(default_factory=list, max_length=5)
    verification_plan: list[str] = Field(default_factory=list, max_length=10)
    prevention: list[str] = Field(default_factory=list, max_length=10)
    eliminated_causes: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode='after')
    def validate_decision(self):
        if self.decision_type in ('TOOL_CALL', 'REQUEST_APPROVAL') and not self.tool:
            raise ValueError('Tool decisions require a tool name')
        if self.decision_type == 'DIAGNOSIS' and (not self.root_cause or not self.evidence_observation_ids):
            raise ValueError('Diagnosis requires root_cause and current observation IDs')
        return self


class CheckSpec(StrictModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    expect: dict[str, Any] = Field(min_length=1)


class ToolMetadata(StrictModel):
    name: str
    description: str
    risk_level: Literal['READ_ONLY', 'LOW_RISK_WRITE', 'HIGH_RISK_WRITE']
    parameters: dict[str, Any]
