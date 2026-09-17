"""The agent's Next steps: what unlocks a guide, and what refuses to.

These run against the real seeded tool catalog, the real training visibility
predicate, and the real contract adapter. A guide that appears here is one an
agent could genuinely open, and a guide that stays hidden is one the server
would refuse at its own route.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.onboarding_tools.models import (
    AgentToolStatus,
    OnboardingTool,
    Provisioning,
    ToolState,
)
from apps.training.audience import AudienceSelector
from apps.training.models import (
    TrainingAudience,
    TrainingContent,
    TrainingEmbed,
    TrainingMedia,
    TrainingProgress,
    TrainingTranscription,
)
from apps.training.taxonomy import CONTENT_TYPE_TOOL_ONBOARDING
from apps.training.tests.factories import office, publish_content
from apps.user.services.onboarding_guides import (
    GuideState,
    activation_guide_payloads,
)
from apps.user.services.onboarding_state import (
    agent_journey_payload,
    journey_for_user,
)
from apps.user.tests.test_profile import completed_user

EMBED = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.fixture
def agent():
    return completed_user(email="agent@example.com")


def tool(slug: str) -> OnboardingTool:
    return OnboardingTool.objects.get(slug=slug)


def invitation_sent(user, slug: str, *, ago: timedelta = timedelta(0)):
    """What an authorized administrator recording a send leaves behind."""
    sent_at = timezone.now() - ago
    AgentToolStatus.objects.update_or_create(
        agent=user,
        tool=tool(slug),
        defaults={
            "state": ToolState.INVITATION_SENT,
            "invitation_sent_at": sent_at,
        },
    )


def set_tool_state(user, slug: str, state: str, **extra):
    AgentToolStatus.objects.update_or_create(
        agent=user, tool=tool(slug), defaults={"state": state, **extra}
    )


def guide(
    *,
    slug: str,
    tool_code: str,
    title: str = "Activate your account",
    playable: bool = True,
    audience: tuple[AudienceSelector, ...] | None = None,
    **fields,
) -> TrainingContent:
    content = publish_content(
        slug=slug,
        title=title,
        owner_office=office("onest-head-office"),
        content_type=CONTENT_TYPE_TOOL_ONBOARDING,
        tool_code=tool_code,
        audience=audience,
    )
    if fields:
        for key, value in fields.items():
            setattr(content, key, value)
        content.save(update_fields=list(fields))
    if playable:
        TrainingEmbed.objects.create(
            content=content,
            url=EMBED,
            provider="youtube",
            host="www.youtube.com",
        )
    return content


def guides_for(user) -> dict:
    return activation_guide_payloads(user, journey_for_user(user))


# --------------------------------------------------------------------------- #
# The unlock, per tool
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_guide_stays_locked_until_this_tools_invitation_is_recorded(agent):
    guide(slug="lofty-activation", tool_code="lofty")

    assert guides_for(agent)["lofty"] == {"state": str(GuideState.LOCKED)}

    invitation_sent(agent, "lofty")
    unlocked = guides_for(agent)["lofty"]
    assert unlocked["state"] == str(GuideState.AVAILABLE)
    assert unlocked["title"] == "Activate your account"


@pytest.mark.django_db
def test_one_tools_invitation_never_unlocks_another_tools_guide(agent):
    guide(slug="lofty-activation", tool_code="lofty")
    guide(slug="skyslope-activation", tool_code="skyslope")

    invitation_sent(agent, "skyslope")

    payloads = guides_for(agent)
    assert payloads["skyslope"]["state"] == str(GuideState.AVAILABLE)
    assert payloads["lofty"] == {"state": str(GuideState.LOCKED)}


@pytest.mark.django_db
def test_a_self_serve_tool_has_no_invitation_to_wait_for(agent):
    onedrive = tool("onedrive")
    assert onedrive.provisioning == Provisioning.SELF_SERVE
    guide(slug="onedrive-activation", tool_code="onedrive")

    assert guides_for(agent)["onedrive"]["state"] == str(GuideState.AVAILABLE)


@pytest.mark.django_db
def test_a_tool_switched_off_for_this_agent_offers_no_guide(agent):
    guide(slug="lofty-activation", tool_code="lofty")
    set_tool_state(agent, "lofty", ToolState.NOT_APPLICABLE)

    assert guides_for(agent)["lofty"] == {"state": str(GuideState.NOT_APPLICABLE)}


@pytest.mark.django_db
def test_a_ready_tool_keeps_its_guide_replayable(agent):
    content = guide(slug="lofty-activation", tool_code="lofty")
    set_tool_state(agent, "lofty", ToolState.READY, ready_at=timezone.now())

    payload = guides_for(agent)["lofty"]
    assert payload["state"] == str(GuideState.AVAILABLE)
    assert payload["contentId"] == content.pk


@pytest.mark.django_db
def test_a_blocked_tool_still_shows_its_unlocked_guide(agent):
    guide(slug="lofty-activation", tool_code="lofty")
    set_tool_state(
        agent,
        "lofty",
        ToolState.BLOCKED,
        invitation_sent_at=timezone.now(),
    )

    assert guides_for(agent)["lofty"]["state"] == str(GuideState.AVAILABLE)


# --------------------------------------------------------------------------- #
# What training refuses to offer
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_an_unlocked_tool_with_no_guide_falls_back_rather_than_breaking(agent):
    invitation_sent(agent, "lofty")

    assert guides_for(agent)["lofty"] == {"state": str(GuideState.UNAVAILABLE)}
    payload = agent_journey_payload(journey_for_user(agent))
    lofty = next(item for item in payload["tools"] if item["key"] == "lofty")
    # The catalog's own fallback travels, so the row has somewhere to send them.
    assert lofty["contact"]


@pytest.mark.django_db
def test_a_self_serve_tool_with_no_guide_says_nothing_rather_than_sending_them_chasing(
    agent,
):
    """OneDrive has setup steps, not an activation video.

    Saying "no activation guide is published" on two dozen self-serve rows is
    noise that points nowhere: the fallback exists for an invitation somebody
    actually sent.
    """
    assert tool("onedrive").provisioning == Provisioning.SELF_SERVE

    assert guides_for(agent)["onedrive"] == {"state": str(GuideState.NOT_APPLICABLE)}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fields",
    [
        pytest.param({"status": TrainingContent.Status.DRAFT}, id="draft"),
        pytest.param({"status": TrainingContent.Status.ARCHIVED}, id="archived"),
    ],
)
def test_unpublished_content_is_never_offered(agent, fields):
    guide(slug="lofty-activation", tool_code="lofty", **fields)
    invitation_sent(agent, "lofty")

    assert guides_for(agent)["lofty"]["state"] == str(GuideState.UNAVAILABLE)


@pytest.mark.django_db
def test_content_outside_its_publication_window_is_never_offered(agent):
    now = timezone.now()
    guide(
        slug="lofty-future",
        tool_code="lofty",
        publish_at=now + timedelta(days=1),
    )
    invitation_sent(agent, "lofty")
    assert guides_for(agent)["lofty"]["state"] == str(GuideState.UNAVAILABLE)

    TrainingContent.objects.filter(slug="lofty-future").update(
        publish_at=now - timedelta(days=2), expires_at=now - timedelta(days=1)
    )
    assert guides_for(agent)["lofty"]["state"] == str(GuideState.UNAVAILABLE)


@pytest.mark.django_db
def test_content_addressed_to_somebody_else_is_never_offered(agent):
    other_office = office("fairfax-va")
    guide(
        slug="lofty-activation",
        tool_code="lofty",
        audience=(
            AudienceSelector(kind=TrainingAudience.Kind.OFFICE, office=other_office),
        ),
    )
    invitation_sent(agent, "lofty")

    assert agent.office != other_office
    assert guides_for(agent)["lofty"]["state"] == str(GuideState.UNAVAILABLE)


@pytest.mark.django_db
def test_content_with_nothing_to_play_is_never_offered(agent):
    guide(slug="lofty-activation", tool_code="lofty", playable=False)
    invitation_sent(agent, "lofty")

    assert guides_for(agent)["lofty"]["state"] == str(GuideState.UNAVAILABLE)


@pytest.mark.django_db
def test_a_recording_still_processing_is_not_a_playable_guide(agent):
    content = guide(slug="lofty-activation", tool_code="lofty", playable=False)
    TrainingMedia.objects.create(
        content=content,
        role=TrainingMedia.Role.PRIMARY,
        processing_state=TrainingMedia.ProcessingState.PENDING,
        display_name="activation.mp4",
        media_type="video/mp4",
        byte_size=1024,
        is_active=True,
    )
    invitation_sent(agent, "lofty")

    assert guides_for(agent)["lofty"]["state"] == str(GuideState.UNAVAILABLE)


@pytest.mark.django_db
def test_a_newer_version_supersedes_the_guide_it_replaces(agent):
    first = guide(slug="lofty-v1", tool_code="lofty", title="Lofty v1")
    second = guide(slug="lofty-v2", tool_code="lofty", title="Lofty v2")
    TrainingContent.objects.filter(pk=second.pk).update(
        version_family=first.version_family, version_number=2
    )
    invitation_sent(agent, "lofty")

    assert guides_for(agent)["lofty"]["contentId"] == second.pk

    # Pulling the replacement falls back to the version before it, not to
    # nothing: an agent mid-activation still has something to watch.
    TrainingContent.objects.filter(pk=second.pk).update(
        status=TrainingContent.Status.ARCHIVED
    )
    assert guides_for(agent)["lofty"]["contentId"] == first.pk


# --------------------------------------------------------------------------- #
# Watching is not activating
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_finishing_the_guide_is_not_the_same_fact_as_a_ready_account(agent):
    content = guide(slug="lofty-activation", tool_code="lofty")
    invitation_sent(agent, "lofty")
    TrainingProgress.objects.create(
        user=agent,
        content=content,
        status=TrainingProgress.Status.COMPLETED,
        completed_at=timezone.now(),
    )

    assert guides_for(agent)["lofty"]["state"] == str(GuideState.COMPLETED)

    payload = agent_journey_payload(journey_for_user(agent))
    lofty = next(item for item in payload["tools"] if item["key"] == "lofty")
    assert lofty["state"] == ToolState.INVITATION_SENT
    assert lofty["complete"] is False


@pytest.mark.django_db
def test_a_transcript_is_advertised_before_the_agent_opens_the_video(agent):
    content = guide(slug="lofty-activation", tool_code="lofty")
    invitation_sent(agent, "lofty")
    assert guides_for(agent)["lofty"]["hasTranscript"] is False

    transcription = TrainingTranscription.objects.create(
        content=content,
        segments=[{"startMs": 0, "endMs": 1200, "text": "Open the invitation."}],
    )
    transcription.rebuild_search_text()
    transcription.save(update_fields=["search_text"])

    assert guides_for(agent)["lofty"]["hasTranscript"] is True


@pytest.mark.django_db
def test_a_part_watched_guide_reads_as_in_progress_not_finished(agent):
    content = guide(slug="lofty-activation", tool_code="lofty")
    invitation_sent(agent, "lofty")
    TrainingProgress.objects.create(
        user=agent,
        content=content,
        status=TrainingProgress.Status.IN_PROGRESS,
        started_at=timezone.now(),
    )

    payload = guides_for(agent)["lofty"]
    assert payload["state"] == str(GuideState.AVAILABLE)
    assert payload["inProgress"] is True


@pytest.mark.django_db
def test_the_guide_payload_carries_no_media_url_or_private_training_field(agent):
    guide(slug="lofty-activation", tool_code="lofty")
    invitation_sent(agent, "lofty")

    payload = guides_for(agent)["lofty"]
    assert set(payload) == {
        "state",
        "contentId",
        "title",
        "summary",
        "estimatedMinutes",
        "href",
        "hasTranscript",
        "inProgress",
    }
    assert EMBED not in str(payload)
    assert payload["href"].startswith("/training-learning/")


# --------------------------------------------------------------------------- #
# The rest of the Next steps contract
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_no_contract_yet_reads_as_waiting_on_the_office_not_as_a_broken_source(agent):
    payload = agent_journey_payload(journey_for_user(agent))

    assert payload["contract"]["state"] == "not_started"
    assert payload["contract"]["label"] == "Waiting for your office administrator"
    assert payload["contract"]["actionHref"] is None
    # Waiting on somebody is not a blocker needing administrator attention.
    assert not any(
        item["key"] == "contract_unavailable" for item in payload["blockers"]
    )


@pytest.mark.django_db
def test_the_inbox_block_names_the_address_without_claiming_a_delivery(agent):
    payload = agent_journey_payload(journey_for_user(agent))

    inbox = payload["invitationInbox"]
    assert inbox["email"] == agent.email
    assert inbox["overdue"] is False
    assert inbox["supportHref"] == "/support/it"


@pytest.mark.django_db
def test_a_recorded_send_becomes_overdue_only_after_the_follow_up_interval(agent):
    invitation_sent(agent, "lofty", ago=timedelta(hours=1))
    assert (
        agent_journey_payload(journey_for_user(agent))["invitationInbox"]["overdue"]
        is False
    )

    invitation_sent(agent, "lofty", ago=timedelta(hours=72))
    assert (
        agent_journey_payload(journey_for_user(agent))["invitationInbox"]["overdue"]
        is True
    )


@pytest.mark.django_db
def test_an_unsent_invitation_is_never_called_overdue(agent):
    set_tool_state(agent, "lofty", ToolState.REQUESTED)

    payload = agent_journey_payload(journey_for_user(agent))
    assert payload["invitationInbox"]["overdue"] is False
