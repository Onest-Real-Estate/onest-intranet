"""Private Centrifugo invalidation stream for the agent onboarding journey.

Domain events are the source of invalidations. This consumer runs after their
owning transaction commits; Centrifugo never holds the journey or its details.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from enum import StrEnum

import httpx
from django.conf import settings
from django.db import transaction

from apps.audit.consumers import is_registered, register_consumer, subscribe
from apps.audit.events import EventEnvelope
from apps.user.models import OnboardingStreamState, User

logger = logging.getLogger(__name__)
CONSUMER_ID = "user.onboarding_stream"


class SourceKey(StrEnum):
    PROFILE = "profile"
    OFFICE = "office"
    OWNERSHIP = "ownership"
    TOOL = "tool"
    CONTRACT = "contract"
    TRAINING = "training"
    BLOCKER = "blocker"
    ACCOUNT = "account"
    ACCESS = "access"


# Centrally registered bridge. New milestone sources join this mapping and
# publish the same four-field client event; no new subscription is needed.
EVENT_SOURCES: dict[str, SourceKey] = {
    "user.onboarded": SourceKey.PROFILE,
    "user.onboarding.profile_changed": SourceKey.PROFILE,
    "user.onboarding.office_changed": SourceKey.OFFICE,
    "user.onboarding.access_changed": SourceKey.ACCESS,
    "user.onboarding.required_setup_completed": SourceKey.PROFILE,
    "user.onboarding.office_handoff_requested": SourceKey.OFFICE,
    "user.onboarding.office_handoff_changed": SourceKey.OFFICE,
    "user.onboarding.owner_assigned": SourceKey.OWNERSHIP,
    "user.onboarding.task_changed": SourceKey.BLOCKER,
    "user.onboarding.tool_setup_changed": SourceKey.TOOL,
    "onboarding_tool.state_changed": SourceKey.TOOL,
    "training.onboarding_progress_changed": SourceKey.TRAINING,
    "user.account.state_changed": SourceKey.ACCOUNT,
    **dict.fromkeys(
        (
            "contract.created",
            "contract.awaiting_company_signature",
            "contract.issued",
            "contract.signed",
            "contract.activated",
            "contract.superseded",
            "contract.terminated",
            "contract.expired",
            "contract.pdf_ready",
            "contract.signed_pdf_ready",
            "contract.viewed",
            "contract.generation_error",
        ),
        SourceKey.CONTRACT,
    ),
}


def configured() -> bool:
    return len(settings.CENTRIFUGO_HMAC_SECRET) >= 32 and all(
        (
            settings.CENTRIFUGO_API_URL,
            settings.CENTRIFUGO_API_KEY,
            settings.CENTRIFUGO_HMAC_SECRET,
            settings.CENTRIFUGO_WS_URL,
        )
    )


def opaque_user_key(user_id: int) -> str:
    digest = hmac.new(
        settings.CENTRIFUGO_HMAC_SECRET.encode(),
        f"onboarding:user:{user_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return digest[:40]


def private_channel(user_id: int) -> str:
    return f"$onboarding:{opaque_user_key(user_id)}"


def state_version(user_id: int) -> int:
    return (
        OnboardingStreamState.objects.filter(user_id=user_id)
        .values_list("version", flat=True)
        .first()
        or 0
    )


def _agent_id(event: EventEnvelope) -> int | None:
    candidate = event.payload.get("user_id") or event.payload.get("agent_id")
    if candidate is None and event.name == "contract.signed":
        from apps.contract.models import AgentContract

        candidate = (
            AgentContract.objects.filter(public_id=event.payload.get("contract_id"))
            .values_list("recipient_id", flat=True)
            .first()
        )
    try:
        return int(candidate) if candidate is not None else None
    except (TypeError, ValueError):
        return None


def _payload(*, event_id: str, source: SourceKey, version: int) -> dict:
    """Exact allowlist: no source event payload is forwarded to Centrifugo."""
    return {
        "id": event_id,
        "eventType": "onboarding.state_changed",
        "sourceKey": source.value,
        "stateVersion": version,
    }


def consume(event: EventEnvelope) -> None:
    source = EVENT_SOURCES.get(event.name)
    if source is None:
        return
    user_id = _agent_id(event)
    if user_id is None or not User.objects.filter(pk=user_id).exists():
        logger.warning("onboarding_live.source_missing source=%s", source.value)
        return

    # Invalidation order is defined by this row lock, not by Celery delivery
    # order. A retry may advance the cursor again; clients still read the DB.
    with transaction.atomic():
        state, _ = OnboardingStreamState.objects.get_or_create(user_id=user_id)
        state = OnboardingStreamState.objects.select_for_update(of=("self",)).get(
            pk=state.pk
        )
        state.version += 1
        state.save(update_fields=["version"])
        version = state.version

    if not configured():
        logger.warning("onboarding_live.unconfigured source=%s", source.value)
        return
    try:
        response = httpx.post(
            f"{settings.CENTRIFUGO_API_URL.rstrip('/')}/api/publish",
            headers={"X-API-Key": settings.CENTRIFUGO_API_KEY},
            json={
                "channel": private_channel(user_id),
                "data": _payload(
                    event_id=str(event.id), source=source, version=version
                ),
            },
            timeout=2.0,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or result.get("error"):
            raise RuntimeError("Centrifugo publish returned an error")
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        logger.warning("onboarding_live.publish_failed source=%s", source.value)
        raise RuntimeError("onboarding live publish failed") from exc
    logger.info("onboarding_live.published source=%s", source.value)


def register_stream_consumer() -> None:
    if is_registered(CONSUMER_ID):
        return
    register_consumer(CONSUMER_ID, consume)
    for event_name in EVENT_SOURCES:
        subscribe(CONSUMER_ID, event_name)
