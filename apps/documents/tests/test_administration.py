"""Documents administration: lifecycle, permissions, concurrency, retention."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import DomainEvent
from apps.documents.administration import (
    StaleDocumentVersion,
    TransitionRefused,
    create_document,
    document_version_token,
    duplicate_version,
    retirement_usage,
    transition,
    update_document,
)
from apps.documents.audience import AudienceSelector, assert_can_target
from apps.documents.media_service import remove_file
from apps.documents.models import DocumentFile, DocumentVersion
from apps.documents.services import LibraryFilters, library_queryset
from apps.documents.tests.factories import (
    agent,
    assign,
    attach_ready_file,
    category,
    office,
    publish_document,
)
from apps.user.models import User
from apps.user.tests.test_profile import completed_user


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


@pytest.fixture(autouse=True)
def isolated_media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def grant(user: User, *codenames: str) -> User:
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="web", codename=codename)
        )
    return User.objects.get(pk=user.pk)


def publisher(*, slug="fairfax-va", email="docs-admin@example.com") -> User:
    user = completed_user(email=email, office=office(slug))
    assign(user, "system_admin", "company")
    return grant(user, "manage_documents", "publish_documents", "retire_documents")


def author_only(*, email="docs-author@example.com") -> User:
    user = completed_user(email=email, office=office("fairfax-va"))
    assign(user, "transaction_coordinator", "office", office("fairfax-va"))
    return grant(user, "manage_documents")


def publisher_without_retire(*, email="docs-publisher@example.com") -> User:
    user = completed_user(email=email, office=office("fairfax-va"))
    assign(user, "marketing_team", "company")
    return grant(user, "manage_documents", "publish_documents")


def regional_publisher(*, email="docs-regional@example.com") -> User:
    user = completed_user(email=email, office=office("region-mid-atlantic"))
    assign(user, "regional_admin", "region", office("region-mid-atlantic"))
    return grant(user, "manage_documents", "publish_documents")


def _draft(actor: User, **overrides) -> DocumentVersion:
    cleaned = {
        "name": "Exclusive buyer agreement",
        "description": "Current approved buyer form",
        "category": category(),
        "effective_at": None,
        "expires_at": None,
        "jurisdiction_state_codes": ["VA"],
        "display_order": 100,
    }
    cleaned.update(overrides)
    return create_document(
        actor=actor,
        office=office("fairfax-va"),
        cleaned=cleaned,
        selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
    )


def _publishable(actor: User, **overrides) -> DocumentVersion:
    draft = _draft(actor, **overrides)
    attach_ready_file(draft, actor=actor)
    return draft


@pytest.mark.django_db
def test_create_draft_publish_emits_domain_event(seeded):
    actor = publisher()
    draft = _publishable(actor)
    assert draft.status == DocumentVersion.Status.DRAFT
    transition(
        actor=actor,
        version=draft,
        action="publish",
        expected_version=document_version_token(draft),
    )
    draft.refresh_from_db()
    assert draft.status == DocumentVersion.Status.PUBLISHED
    assert DomainEvent.objects.filter(name="document.published").exists()
    reader = agent()
    assert library_queryset(reader, LibraryFilters()).filter(pk=draft.pk).exists()


@pytest.mark.django_db
def test_duplicate_version_and_publish_supersedes_previous(seeded):
    actor = publisher()
    live = publish_document(
        key="compliance-pack",
        name="Compliance pack",
        owner_office=office("fairfax-va"),
        audience=(AudienceSelector(kind="office", office=office("fairfax-va")),),
    )
    draft = duplicate_version(
        actor=actor, version=live, expected_version=document_version_token(live)
    )
    assert draft.status == DocumentVersion.Status.DRAFT
    assert draft.family.pk == live.family.pk
    assert draft.version_number == 2
    assert DocumentFile.objects.filter(document_version=draft, is_active=True).exists()

    transition(
        actor=actor,
        version=draft,
        action="publish",
        expected_version=document_version_token(draft),
    )
    live.refresh_from_db()
    draft.refresh_from_db()
    assert draft.status == DocumentVersion.Status.PUBLISHED
    assert live.status == DocumentVersion.Status.SUPERSEDED
    assert DomainEvent.objects.filter(name="document.published").exists()
    assert DomainEvent.objects.filter(name="document.superseded").exists()


@pytest.mark.django_db
def test_schedule_caps_sibling_window_and_refuses_overlap(seeded):
    actor = publisher()
    live = _publishable(actor, name="Windowed form")
    transition(
        actor=actor,
        version=live,
        action="publish",
        expected_version=document_version_token(live),
    )
    live.refresh_from_db()
    replacement = duplicate_version(
        actor=actor, version=live, expected_version=document_version_token(live)
    )
    start = timezone.now() + timedelta(days=7)
    update_document(
        actor=actor,
        version=replacement,
        cleaned={
            "name": replacement.name,
            "description": replacement.description,
            "category": replacement.category,
            "effective_at": start,
            "expires_at": None,
            "jurisdiction_state_codes": list(replacement.jurisdiction_state_codes),
            "display_order": replacement.display_order,
        },
        selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
        expected_version=document_version_token(replacement),
    )
    replacement.refresh_from_db()
    transition(
        actor=actor,
        version=replacement,
        action="schedule",
        expected_version=document_version_token(replacement),
    )
    live.refresh_from_db()
    replacement.refresh_from_db()
    assert replacement.status == DocumentVersion.Status.PUBLISHED
    assert live.status == DocumentVersion.Status.PUBLISHED
    assert live.expires_at == start
    assert DomainEvent.objects.filter(name="document.scheduled").exists()
    reader = agent()
    visible = set(
        library_queryset(reader, LibraryFilters()).values_list("pk", flat=True)
    )
    assert live.pk in visible
    assert replacement.pk not in visible

    colliding = duplicate_version(
        actor=actor,
        version=replacement,
        expected_version=document_version_token(replacement),
    )
    earlier = start - timedelta(days=1)
    update_document(
        actor=actor,
        version=colliding,
        cleaned={
            "name": colliding.name,
            "description": colliding.description,
            "category": colliding.category,
            "effective_at": earlier,
            "expires_at": None,
            "jurisdiction_state_codes": list(colliding.jurisdiction_state_codes),
            "display_order": colliding.display_order,
        },
        selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
        expected_version=document_version_token(colliding),
    )
    colliding.refresh_from_db()
    with pytest.raises(TransitionRefused):
        transition(
            actor=actor,
            version=colliding,
            action="schedule",
            expected_version=document_version_token(colliding),
        )


@pytest.mark.django_db
def test_assert_can_target_denies_company_for_non_company_admin(seeded):
    actor = regional_publisher()
    with pytest.raises(PermissionDenied):
        assert_can_target(actor, [AudienceSelector(kind="company")])


@pytest.mark.django_db
def test_scoped_publisher_cannot_cover_all_states(seeded):
    actor = regional_publisher()
    with pytest.raises(PermissionDenied):
        create_document(
            actor=actor,
            office=office("region-mid-atlantic"),
            cleaned={
                "name": "Nationwide form",
                "description": "",
                "category": category(),
                "effective_at": None,
                "expires_at": None,
                "jurisdiction_state_codes": [],
                "display_order": 100,
            },
            selectors=[
                AudienceSelector(kind="region", office=office("region-mid-atlantic"))
            ],
        )


@pytest.mark.django_db
def test_stale_version_returns_409_on_update(seeded, client: Client):
    actor = publisher()
    draft = _draft(actor)
    assert draft.category is not None
    client.force_login(actor)
    response = client.post(
        reverse("document_admin_update", args=[draft.pk]),
        data=json.dumps(
            {
                "name": "Changed title",
                "description": draft.description,
                "category": draft.category.code,
                "audience_offices": [str(office("fairfax-va").pk)],
                "expected_version": "not-the-token",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_stale_version_refuses_service_update(seeded):
    actor = publisher()
    draft = _draft(actor)
    with pytest.raises(StaleDocumentVersion):
        update_document(
            actor=actor,
            version=draft,
            cleaned={"name": "Changed"},
            selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
            expected_version="not-the-token",
        )


@pytest.mark.django_db
def test_json_create_path(seeded, client: Client):
    actor = publisher()
    client.force_login(actor)
    response = client.post(
        reverse("document_admin_create"),
        data=json.dumps(
            {
                "owner_office": str(office("fairfax-va").pk),
                "name": "JSON draft",
                "description": "",
                "category": "listing",
                "display_order": 100,
                "audience_offices": [str(office("fairfax-va").pk)],
            }
        ),
        content_type="application/json",
    )
    assert response.status_code in {302, 303}, response.content[:2000]
    assert DocumentVersion.objects.filter(name="JSON draft").exists()


@pytest.mark.django_db
def test_create_sheet_defaults_display_order_when_omitted(seeded, client: Client):
    actor = publisher()
    client.force_login(actor)
    response = client.post(
        reverse("document_admin_create"),
        data=json.dumps(
            {
                "owner_office": str(office("fairfax-va").pk),
                "name": "No order field",
                "description": "Summary",
                "category": "listing",
                "audience_company": "on",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code in {302, 303}, response.content[:2000]
    created = DocumentVersion.objects.get(name="No order field")
    assert created.display_order == 100


@pytest.mark.django_db
def test_manage_without_publish_cannot_go_live(seeded, client: Client):
    actor = author_only()
    draft = _publishable(actor)
    with pytest.raises(PermissionDenied):
        transition(
            actor=actor,
            version=draft,
            action="publish",
            expected_version=document_version_token(draft),
        )
    client.force_login(actor)
    response = client.post(
        reverse("document_admin_lifecycle", args=[draft.pk]),
        data=json.dumps(
            {
                "action": "publish",
                "expected_version": document_version_token(draft),
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 403
    draft.refresh_from_db()
    assert draft.status == DocumentVersion.Status.DRAFT


@pytest.mark.django_db
def test_publish_without_retire_cannot_retire(seeded, client: Client):
    actor = publisher_without_retire()
    draft = _publishable(actor)
    live = transition(
        actor=actor,
        version=draft,
        action="publish",
        expected_version=document_version_token(draft),
    )
    with pytest.raises(PermissionDenied):
        transition(
            actor=actor,
            version=live,
            action="retire",
            expected_version=document_version_token(live),
        )
    client.force_login(actor)
    response = client.post(
        reverse("document_admin_lifecycle", args=[live.pk]),
        data=json.dumps(
            {
                "action": "retire",
                "expected_version": document_version_token(live),
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 403
    live.refresh_from_db()
    assert live.status == DocumentVersion.Status.PUBLISHED


@pytest.mark.django_db
def test_retire_reports_usage_emits_event_and_leaves_library(seeded):
    actor = publisher()
    draft = _publishable(actor, name="Retiring form")
    live = transition(
        actor=actor,
        version=draft,
        action="publish",
        expected_version=document_version_token(draft),
    )
    usage = retirement_usage(live)
    assert usage["isCurrent"] is True
    assert usage["fileCount"] == 1
    assert usage["wouldLeaveFamilyWithoutCurrent"] is True

    retired = transition(
        actor=actor,
        version=live,
        action="retire",
        expected_version=document_version_token(live),
    )
    assert retired.status == DocumentVersion.Status.RETIRED
    assert DomainEvent.objects.filter(name="document.retired").exists()
    reader = agent()
    assert not library_queryset(reader, LibraryFilters()).filter(pk=retired.pk).exists()


@pytest.mark.django_db
def test_remove_file_deactivates_and_keeps_bytes(seeded):
    actor = publisher()
    draft = _publishable(actor)
    row = DocumentFile.objects.get(document_version=draft)
    storage_name = row.file.name
    remove_file(actor, row)
    row.refresh_from_db()
    assert row.is_active is False
    assert row.file.storage.exists(storage_name)


@pytest.mark.django_db
def test_published_files_cannot_be_removed(seeded):
    actor = publisher()
    live = publish_document(
        key="locked-file",
        name="Locked file",
        owner_office=office("fairfax-va"),
        audience=(AudienceSelector(kind="office", office=office("fairfax-va")),),
    )
    row = DocumentFile.objects.get(document_version=live)
    with pytest.raises(ValidationError):
        remove_file(actor, row)
    row.refresh_from_db()
    assert row.is_active is True


@pytest.mark.django_db
def test_admin_preview_uses_manage_scope_not_consumer_current(seeded, client: Client):
    actor = publisher()
    v1 = publish_document(
        key="preview-family",
        name="Old file",
        owner_office=office("fairfax-va"),
        audience=(AudienceSelector(kind="office", office=office("fairfax-va")),),
        version_number=1,
    )
    old_file = DocumentFile.objects.get(document_version=v1)
    publish_document(
        key="preview-family",
        name="New file",
        owner_office=office("fairfax-va"),
        audience=(AudienceSelector(kind="office", office=office("fairfax-va")),),
        version_number=2,
    )
    v1.status = DocumentVersion.Status.SUPERSEDED
    v1.save(update_fields=["status"])

    reader = agent()
    client.force_login(reader)
    denied = client.get(reverse("document_file", args=[old_file.pk]))
    assert denied.status_code == 404

    client.force_login(actor)
    preview = client.get(
        reverse("document_admin_file", args=[old_file.pk]), {"preview": "1"}
    )
    assert preview.status_code == 200
    assert preview["Cache-Control"].startswith("private, no-store")
    disposition = preview.get("Content-Disposition", "")
    assert "inline" in disposition or "attachment" not in disposition.lower()


@pytest.mark.django_db
def test_administration_index_lists_versions_in_scope(seeded, client: Client):
    actor = publisher()
    _draft(actor, name="Scoped draft")
    client.force_login(actor)
    response = client.get(reverse("admin_documents"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["component"] == "DocumentsAdministration"
    names = {row["name"] for row in payload["props"]["documents"]["items"]}
    assert "Scoped draft" in names
    assert payload["props"]["capabilities"]["canAuthor"] is True
    assert payload["props"]["capabilities"]["canPublish"] is True
    assert payload["props"]["capabilities"]["canRetire"] is True
