"""Protected training media streaming."""

from __future__ import annotations

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse

from apps.training.audience import AudienceSelector
from apps.training.models import TrainingAudience, TrainingMedia
from apps.training.tests.factories import agent, office, publish_content


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def _media_for(
    content, *, state=TrainingMedia.ProcessingState.READY, tmp_path, settings
):
    settings.MEDIA_ROOT = str(tmp_path)
    media = TrainingMedia(
        content=content,
        role=TrainingMedia.Role.PRIMARY,
        display_name="guide.pdf",
        media_type="application/pdf",
        byte_size=5,
        checksum="x" * 64,
        processing_state=state,
    )
    media.file.save("guide.pdf", ContentFile(b"hello"), save=False)
    media.save()
    return media


def test_in_audience_reader_can_stream_media(seeded, client, settings, tmp_path):
    reader = agent()
    content = publish_content(
        slug="with-file",
        title="With file",
        owner_office=office("onest-head-office"),
    )
    media = _media_for(content, tmp_path=tmp_path, settings=settings)

    client.force_login(reader)
    response = client.get(reverse("training_media", args=[media.pk]))
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"hello"
    assert "private" in response["Cache-Control"]


def test_out_of_audience_reader_is_denied(seeded, client, settings, tmp_path):
    reader = agent()
    content = publish_content(
        slug="private-file",
        title="Private file",
        owner_office=office("onest-head-office"),
        audience=(
            AudienceSelector(
                kind=TrainingAudience.Kind.ROLE,
                role="system_admin",
            ),
        ),
    )
    media = _media_for(content, tmp_path=tmp_path, settings=settings)

    client.force_login(reader)
    assert client.get(reverse("training_media", args=[media.pk])).status_code == 403


def test_pending_media_is_not_streamed(seeded, client, settings, tmp_path):
    reader = agent()
    content = publish_content(
        slug="processing",
        title="Processing",
        owner_office=office("onest-head-office"),
    )
    media = _media_for(
        content,
        state=TrainingMedia.ProcessingState.PENDING,
        tmp_path=tmp_path,
        settings=settings,
    )

    client.force_login(reader)
    assert client.get(reverse("training_media", args=[media.pk])).status_code == 403
