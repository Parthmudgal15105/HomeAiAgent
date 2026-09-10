from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


def uuid() -> str:
    return str(uuid4())


class Incident(Base):
    __tablename__ = 'incidents'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default='')
    service: Mapped[str] = mapped_column(String(100), default='codeduel')
    status: Mapped[str] = mapped_column(String(32), default='OPEN', index=True)
    severity: Mapped[str] = mapped_column(String(20), default='MEDIUM')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    root_cause: Mapped[str | None] = mapped_column(Text)
    root_cause_confidence: Mapped[float | None] = mapped_column(Float)
    summary: Mapped[str | None] = mapped_column(Text)
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    agent_state: Mapped[dict] = mapped_column(JSON, default=dict)
    observations: Mapped[list['Observation']] = relationship(back_populates='incident', cascade='all, delete-orphan', order_by='Observation.step_number')
    hypotheses: Mapped[list['Hypothesis']] = relationship(back_populates='incident', cascade='all, delete-orphan')
    actions: Mapped[list['Action']] = relationship(back_populates='incident', cascade='all, delete-orphan', order_by='Action.created_at')


class Observation(Base):
    __tablename__ = 'observations'
    __table_args__ = (UniqueConstraint('incident_id', 'step_number'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    incident_id: Mapped[str] = mapped_column(ForeignKey('incidents.id', ondelete='CASCADE'), index=True)
    step_number: Mapped[int] = mapped_column(Integer)
    tool_name: Mapped[str] = mapped_column(String(80))
    tool_arguments: Mapped[dict] = mapped_column(JSON)
    raw_result: Mapped[dict] = mapped_column(JSON)
    normalized_result: Mapped[dict] = mapped_column(JSON)
    interpretation: Mapped[str] = mapped_column(Text, default='')
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    phase: Mapped[str] = mapped_column(String(24), default='INVESTIGATION')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    incident: Mapped[Incident] = relationship(back_populates='observations')


class Hypothesis(Base):
    __tablename__ = 'hypotheses'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    incident_id: Mapped[str] = mapped_column(ForeignKey('incidents.id', ondelete='CASCADE'), index=True)
    description: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(24), default='ACTIVE')
    supporting_observation_ids: Mapped[list] = mapped_column(JSON, default=list)
    contradicting_observation_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    incident: Mapped[Incident] = relationship(back_populates='hypotheses')


class Action(Base):
    __tablename__ = 'actions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    incident_id: Mapped[str] = mapped_column(ForeignKey('incidents.id', ondelete='CASCADE'), index=True)
    tool_name: Mapped[str] = mapped_column(String(80))
    arguments: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(24), default='LOW_RISK_WRITE')
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    approval_status: Mapped[str] = mapped_column(String(24), default='PENDING')
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    verification_status: Mapped[str] = mapped_column(String(24), default='NOT_RUN')
    incident: Mapped[Incident] = relationship(back_populates='actions')


class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey('incidents.id', ondelete='CASCADE'), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EvaluationRun(Base):
    __tablename__ = 'evaluation_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid)
    provider: Mapped[str] = mapped_column(String(100))
    metrics: Mapped[dict] = mapped_column(JSON)
    results: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
