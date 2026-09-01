"""Shared test helpers for training."""

from __future__ import annotations

from django.utils import timezone

from apps.training.audience import AudienceSelector
from apps.training.models import (
    TrainingAudience,
    TrainingCategory,
    TrainingContent,
    TrainingEmbed,
    TrainingTranscription,
)
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.tests.test_profile import completed_user


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def category(code: str = "general") -> TrainingCategory:
    return TrainingCategory.objects.get(code=code)


def assign(user, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def agent(slug="fairfax-va", email="agent@example.com") -> User:
    return completed_user(email=email, office=office(slug))


def _apply_audience(
    content: TrainingContent,
    audience: tuple[AudienceSelector, ...],
) -> None:
    TrainingAudience.objects.filter(content=content).delete()
    TrainingAudience.objects.bulk_create(
        [
            TrainingAudience(
                content=content,
                kind=selector.kind,
                role=selector.role
                if selector.kind == TrainingAudience.Kind.ROLE
                else "",
                office=selector.office
                if selector.kind
                in {TrainingAudience.Kind.REGION, TrainingAudience.Kind.OFFICE}
                else None,
                user=selector.user
                if selector.kind == TrainingAudience.Kind.USER
                else None,
            )
            for selector in audience
        ]
    )


def publish_content(
    *,
    slug: str,
    title: str,
    owner_office: Office,
    content_type: str = "article",
    body: str = "Training body",
    is_required: bool = False,
    audience: tuple[AudienceSelector, ...] | None = None,
    tool_code: str = "",
) -> TrainingContent:
    content = TrainingContent.objects.create(
        owner_office=owner_office,
        slug=slug,
        title=title,
        summary="Summary",
        body=body,
        content_type=content_type,
        category=category(),
        is_required=is_required,
        tool_code=tool_code,
        status=TrainingContent.Status.PUBLISHED,
        published_at=timezone.now(),
    )
    selectors = audience or (AudienceSelector(kind=TrainingAudience.Kind.COMPANY),)
    _apply_audience(content, selectors)
    return content


def video_with_transcription(
    *,
    slug: str,
    title: str,
    owner_office: Office,
    segments: list[dict],
) -> TrainingContent:
    content = publish_content(
        slug=slug,
        title=title,
        owner_office=owner_office,
        content_type="video",
        body="",
    )
    TrainingEmbed.objects.create(
        content=content,
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        provider="youtube",
        host="www.youtube.com",
    )
    transcription = TrainingTranscription.objects.create(
        content=content, segments=segments
    )
    transcription.rebuild_search_text()
    transcription.save(update_fields=["search_text"])
    return content
