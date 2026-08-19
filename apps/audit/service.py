from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.db import transaction
from django.forms.models import model_to_dict
from django.utils import timezone

from apps.audit.context import get_audit_context
from apps.audit.models import AuditEvent

SENSITIVE_FRAGMENTS = frozenset(
    {
        "password",
        "token",
        "secret",
        "credential",
        "ssn",
        "credit_card",
        "cvv",
        "document",
        "content",
        "headshot",
        "street_address",
        "zip_code",
        "phone",
        "email",
    }
)

MAX_STRING = 500
MAX_COLLECTION = 100


@dataclass
class AuditActor:
    actor_type: str
    actor_id: str = ""
    actor_label: str = ""
    actor_snapshot: dict[str, Any] | None = None


@dataclass
class AuditTarget:
    target_type: str
    target_id: str = ""
    target_label: str = ""
    target_snapshot: dict[str, Any] | None = None


def _sanitize_string(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").strip()[:MAX_STRING]


def redact(value: Any, path: str = "") -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            full_key = f"{path}.{key}" if path else key
            if any(frag in full_key.lower() for frag in SENSITIVE_FRAGMENTS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact(item, full_key)
        return redacted
    if isinstance(value, list):
        return [redact(item, path) for item in value[:MAX_COLLECTION]]
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str):
        return _sanitize_string(value)
    return value


def snapshot_model(instance, *, fields: list[str] | None = None) -> dict[str, Any]:
    if instance is None:
        return {}
    if fields is None:
        fields = [field.name for field in instance._meta.fields]
    return redact(model_to_dict(instance, fields=fields))


def diff_changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    keys = sorted(set(before) | set(after))
    changes = {}
    for key in keys:
        if before.get(key) != after.get(key):
            changes[key] = {"before": before.get(key), "after": after.get(key)}
    return redact(changes)


def actor_from_user(user) -> AuditActor:
    if user is None:
        return AuditActor(
            actor_type=AuditEvent.ActorType.ANONYMOUS,
            actor_label="anonymous",
        )
    actor_id = str(getattr(user, "pk", "") or "")
    label = getattr(user, "email", "") or getattr(user, "display_name", "") or str(user)
    snapshot = {
        "id": actor_id,
        "email": getattr(user, "email", ""),
        "display_name": getattr(user, "display_name", ""),
        "office_id": str(getattr(user, "office_id", "") or ""),
    }
    return AuditActor(
        actor_type=AuditEvent.ActorType.USER,
        actor_id=actor_id,
        actor_label=_sanitize_string(label),
        actor_snapshot=redact(snapshot),
    )


def target_from_instance(instance, *, label: str | None = None) -> AuditTarget:
    if instance is None:
        return AuditTarget(target_type="unknown")
    object_name = instance._meta.label_lower
    target_id = str(getattr(instance, "pk", "") or "")
    target_label = label or getattr(instance, "name", "") or str(instance)
    return AuditTarget(
        target_type=object_name,
        target_id=target_id,
        target_label=_sanitize_string(target_label),
        target_snapshot=snapshot_model(instance),
    )


def log_event(
    action: str,
    *,
    actor: AuditActor,
    target: AuditTarget,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    organization_id: str = "",
    office_id: str = "",
    region_id: str = "",
    source: str = "",
    channel: str = "",
    outcome: str = AuditEvent.Outcome.SUCCESS,
    reason: str = "",
    metadata: dict[str, Any] | None = None,
    payload_version: int = 1,
    occurred_at=None,
):
    ctx = get_audit_context()
    before = redact(before or {})
    after = redact(after or {})
    changes = diff_changes(before, after)
    event = AuditEvent(
        payload_version=payload_version,
        action=_sanitize_string(action),
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        actor_label=actor.actor_label,
        actor_snapshot=redact(actor.actor_snapshot or {}),
        impersonated_by=redact(ctx.impersonated_by),
        target_type=target.target_type,
        target_id=target.target_id,
        target_label=target.target_label,
        target_snapshot=redact(target.target_snapshot or {}),
        organization_id=_sanitize_string(organization_id),
        office_id=_sanitize_string(office_id),
        region_id=_sanitize_string(region_id),
        source=_sanitize_string(source or ctx.source or "app")[:64],
        channel=_sanitize_string(channel or ctx.channel)[:64],
        request_id=_sanitize_string(ctx.request_id)[:255],
        correlation_id=ctx.correlation_id,
        remote_addr=_sanitize_string(ctx.remote_addr)[:128],
        user_agent=_sanitize_string(ctx.user_agent)[:512],
        outcome=outcome,
        reason=_sanitize_string(reason),
        before=before,
        after=after,
        changes=changes,
        metadata=redact(metadata or ctx.metadata or {}),
        occurred_at=occurred_at or timezone.now(),
    )
    event.save()
    return event


def log_model_change(
    action: str,
    *,
    actor: AuditActor,
    instance,
    before_instance=None,
    snapshot_fields: list[str] | None = None,
    outcome: str = AuditEvent.Outcome.SUCCESS,
    reason: str = "",
    metadata: dict[str, Any] | None = None,
):
    before = snapshot_model(before_instance, fields=snapshot_fields)
    after = snapshot_model(instance, fields=snapshot_fields)
    office_id = str(getattr(instance, "office_id", "") or "")
    region = getattr(instance, "region", None)
    region_id = ""
    if region is not None:
        region_id = str(getattr(region, "stable_key", "") or getattr(region, "pk", ""))
    return log_event(
        action,
        actor=actor,
        target=target_from_instance(instance),
        before=before,
        after=after,
        office_id=office_id,
        region_id=region_id,
        outcome=outcome,
        reason=reason,
        metadata=metadata,
    )


def log_on_commit(*args, **kwargs):
    transaction.on_commit(lambda: log_event(*args, **kwargs))


def system_actor(label: str = "system") -> AuditActor:
    return AuditActor(
        actor_type=AuditEvent.ActorType.SYSTEM,
        actor_id=label,
        actor_label=label,
        actor_snapshot={"label": label},
    )


def service_actor(label: str) -> AuditActor:
    return AuditActor(
        actor_type=AuditEvent.ActorType.SERVICE,
        actor_id=label,
        actor_label=label,
        actor_snapshot={"label": label},
    )
