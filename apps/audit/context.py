from __future__ import annotations

import contextvars
import uuid
from dataclasses import dataclass, field


@dataclass
class AuditContext:
    request_id: str = ""
    source: str = "app"
    channel: str = ""
    remote_addr: str = ""
    user_agent: str = ""
    correlation_id: uuid.UUID | None = None
    impersonated_by: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


_audit_context: contextvars.ContextVar[AuditContext | None] = contextvars.ContextVar(
    "audit_context",
    default=None,
)


def get_audit_context() -> AuditContext:
    return _audit_context.get() or AuditContext()


def set_audit_context(ctx: AuditContext):
    return _audit_context.set(ctx)


def reset_audit_context(token) -> None:
    _audit_context.reset(token)
