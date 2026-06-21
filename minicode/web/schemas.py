"""Validated REST request and response models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


TurnStatus = Literal[
    "idle",
    "running",
    "waiting_permission",
    "failed",
    "incomplete",
    "completed",
    "cancelled",
]


class CreateSessionRequest(BaseModel):
    title: str = Field(default="", max_length=120)


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)


class PermissionResolveRequest(BaseModel):
    decision: Literal[
        "allow_once",
        "allow_always",
        "allow_turn",
        "allow_all_turn",
        "deny_once",
        "deny_always",
        "deny_with_feedback",
    ]
    feedback: str = Field(default="", max_length=2_000)


class SessionSummary(BaseModel):
    sessionId: str
    createdAt: float
    updatedAt: float
    title: str
    messageCount: int
    status: TurnStatus


class SessionSnapshot(BaseModel):
    sessionId: str
    workspace: str
    status: TurnStatus
    activeTurnId: str = ""
    lastSeq: int = 0
    messages: list[dict[str, Any]] = Field(default_factory=list)
    activities: list[dict[str, Any]] = Field(default_factory=list)
    pendingPermissions: list[dict[str, Any]] = Field(default_factory=list)
    error: dict[str, Any] | None = None
    terminal: dict[str, Any] | None = None


class DiffFile(BaseModel):
    path: str
    additions: int
    deletions: int
    status: str = "modified"
    isBinary: bool = False


class DiffResponse(BaseModel):
    files: list[DiffFile]
    additions: int
    deletions: int
    truncated: bool = False
    revision: str = ""


class DiffPatchResponse(BaseModel):
    path: str
    patch: str
    additions: int
    deletions: int
    status: str = "modified"
    isBinary: bool = False
    truncated: bool = False
    revision: str = ""


class ErrorDetail(BaseModel):
    code: str
    message: str
    traceId: str
    retryable: bool


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
