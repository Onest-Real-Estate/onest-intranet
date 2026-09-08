from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event, service_actor
from apps.user.models import User
from apps.user.services.role_assignments import has_effective_permission


@dataclass(frozen=True)
class ReplayInitiator:
    actor_type: str
    actor_id: str
    request_id: str = ""


def request_replay_event(
    *,
    actor: User,
    event_id: str,
    consumer_id: str | None = None,
    request_id: str = "",
) -> None:
    if not (
        getattr(actor, "is_superuser", False)
        or has_effective_permission(actor, "audit.can_replay_events")
    ):
        log_event(
            "audit.event_replay.denied",
            actor=actor_from_user(actor),
            target=AuditTarget(target_type="audit.domain_event", target_id=event_id),
            outcome=AuditEvent.Outcome.DENIED,
            source="request",
            channel="admin",
            reason="missing_permissions",
            metadata={"request_id": request_id, "consumer_id": consumer_id or ""},
        )
        raise PermissionDenied("You do not have permission to replay events.")

    from apps.audit.tasks import replay_event

    replay_event.delay(
        event_id,
        consumer_id,
        {
            "actor_type": AuditEvent.ActorType.USER,
            "actor_id": str(actor.pk),
            "request_id": request_id,
        },
    )


def system_replay_initiator(label: str) -> dict[str, str]:
    return {
        "actor_type": AuditEvent.ActorType.SERVICE,
        "actor_id": label,
        "request_id": "",
    }


def revalidate_replay_initiator(
    initiator: dict[str, str] | None,
    *,
    event_id: str,
    consumer_id: str | None = None,
) -> bool:
    if not initiator:
        log_event(
            "audit.event_replay.denied",
            actor=service_actor("audit.replay_event"),
            target=AuditTarget(target_type="audit.domain_event", target_id=event_id),
            outcome=AuditEvent.Outcome.DENIED,
            source="task",
            channel="celery",
            reason="missing_initiator",
            metadata={"consumer_id": consumer_id or ""},
        )
        return False

    if initiator.get("actor_type") == AuditEvent.ActorType.SERVICE:
        return True

    actor_id = initiator.get("actor_id")
    if not actor_id:
        return False
    user = User.objects.filter(pk=actor_id).first()
    if user is None:
        return False
    if getattr(user, "is_superuser", False) or has_effective_permission(
        user, "audit.can_replay_events"
    ):
        return True

    log_event(
        "audit.event_replay.denied",
        actor=actor_from_user(user),
        target=AuditTarget(target_type="audit.domain_event", target_id=event_id),
        outcome=AuditEvent.Outcome.DENIED,
        source="task",
        channel="celery",
        reason="initiator_lost_permission",
        metadata={
            "request_id": initiator.get("request_id", ""),
            "consumer_id": consumer_id or "",
        },
    )
    return False
