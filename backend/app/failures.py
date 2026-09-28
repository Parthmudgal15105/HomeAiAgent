"""Stable, non-secret failure categories for the bounded controller."""
from __future__ import annotations

import asyncio
from enum import StrEnum

import httpx
from pydantic import ValidationError


class FailureKind(StrEnum):
    MODEL_TIMEOUT = 'MODEL_TIMEOUT'
    MODEL_UNAVAILABLE = 'MODEL_UNAVAILABLE'
    MODEL_INVALID_OUTPUT = 'MODEL_INVALID_OUTPUT'
    TOOL_TIMEOUT = 'TOOL_TIMEOUT'
    TOOL_FAILURE = 'TOOL_FAILURE'
    INFRASTRUCTURE_FAILURE = 'INFRASTRUCTURE_FAILURE'


def model_failure_kind(error: BaseException) -> FailureKind:
    """Classify a model boundary error without exposing provider internals."""
    if isinstance(error, (asyncio.TimeoutError, httpx.TimeoutException)):
        return FailureKind.MODEL_TIMEOUT
    if isinstance(error, httpx.HTTPStatusError):
        return FailureKind.MODEL_UNAVAILABLE
    message = str(error).casefold()
    if any(marker in message for marker in ('unavailable', 'connection refused', 'connection failed', 'service error', 'http 429', 'http 502', 'http 503')):
        return FailureKind.MODEL_UNAVAILABLE
    if isinstance(error, (ValidationError, ValueError)):
        return FailureKind.MODEL_INVALID_OUTPUT
    if isinstance(error, (httpx.RequestError, OSError, ConnectionError)):
        return FailureKind.MODEL_UNAVAILABLE
    return FailureKind.INFRASTRUCTURE_FAILURE


def tool_failure_kind(error: BaseException | str | None) -> FailureKind:
    """Classify an execution envelope or transport exception deterministically."""
    if isinstance(error, (asyncio.TimeoutError, httpx.TimeoutException)):
        return FailureKind.TOOL_TIMEOUT
    if isinstance(error, (httpx.RequestError, OSError, ConnectionError)):
        return FailureKind.INFRASTRUCTURE_FAILURE
    message = str(error or '').casefold()
    if 'timeout' in message or 'timed out' in message or 'deadline' in message:
        return FailureKind.TOOL_TIMEOUT
    return FailureKind.TOOL_FAILURE
