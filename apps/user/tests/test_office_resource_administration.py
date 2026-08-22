"""Scoped office resources administration tests.

Covers the grant matrix (branch / regional / company), ownership and shadow
boundaries, optimistic concurrency, server-side validation, file lifecycle,
archive semantics, cache invalidation, and audit events.
"""

from __future__ import annotations

import json

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.user.models import Office, OfficeResource, UserRoleAssignment
from apps.user.services.office_resource_administration import (
    StaleResourceVersion,
    create_resource,
    detail_payload,
    managed_resource_queryset,
    resource_scope,
    resource_version,
    transition_resource,
    update_resource,
)
from apps.user.tests.test_profile import completed_user


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def props(response) -> dict:
    return json.loads(response.content)["props"]


def assign(user, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


@pytest.fixture
def org(seeded_offices):
    """One region with two branches, seeded offices provide the rest."""
    return None


@pytest.fixture
def seeded_offices():
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    # Grant current catalog permissions (incl. the resource console) to groups.
    seed_brokerage_roles()
    seed_offices()


def branch_admin(email="branch.admin@example.com", slug="fairfax-va"):
    user = completed_user(email=email, office=office(slug))
    assign(user, "branch_admin", "office", office(slug))
    return user


def regional_admin(slug="region-mid-atlantic", seat="harrisburg"):
    user = completed_user(email=f"regional.{slug}@example.com", office=office(seat))
    assign(user, "regional_admin", "region", office(slug))
    return user


def company_admin():
    user = completed_user(
        email="company.admin@example.com", office=office("onest-head-office")
    )
    assign(user, "system_admin", "company")
    return user


def plain_agent(slug="fairfax-va"):
    return completed_user(email="agent@example.com", office=office(slug))


def make(office_node, slug, **kwargs) -> OfficeResource:
    resource = OfficeResource(
        owner_office=office_node,
        slug=slug,
        title=kwargs.pop("title", slug.replace("-", " ").title()),
        category=kwargs.pop("category", "general"),
        resource_type=kwargs.pop("resource_type", "content"),
        body=kwargs.pop("body", "Instructions here."),
        **kwargs,
    )
    exclude = {"created_by"}
    if resource.resource_type == "file" and not resource.file:
        # Tests attach files after creation; save without validation since
        # the model deliberately refuses file-less file resources.
        resource.save()
        return resource
    resource.full_clean(exclude=exclude)
    resource.save()
    return resource


# ---------------------------------------------------------------------------
# Grant matrix + scope boundaries
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_branch_admin_scope_covers_own_office_only(seeded_offices):
    actor = branch_admin()
    scope = resource_scope(actor)
    assert office("fairfax-va").pk in scope.office_ids
    assert office("charlottesville-va").pk not in scope.office_ids
    assert office("onest-head-office").pk not in scope.office_ids
    assert not scope.includes_company


@pytest.mark.django_db
def test_regional_admin_scope_covers_region_descendants(seeded_offices):
    actor = regional_admin()
    scope = resource_scope(actor)
    assert office("region-mid-atlantic").pk in scope.office_ids
    assert office("harrisburg").pk in scope.office_ids
    assert office("philadelphia").pk in scope.office_ids
    assert office("connecticut").pk not in scope.office_ids  # New England
    assert office("onest-head-office").pk not in scope.office_ids


@pytest.mark.django_db
def test_company_admin_scope_covers_everything(seeded_offices):
    from apps.user.services.office_resource_administration import (
        can_publish_company,
    )

    actor = company_admin()
    scope = resource_scope(actor)
    assert scope.includes_company
    assert office("onest-head-office").pk in scope.office_ids
    assert can_publish_company(actor)


@pytest.mark.django_db
def test_index_requires_view_permission(client, seeded_offices):
    client.force_login(plain_agent())
    assert (
        client.get(reverse("admin_office_resources"), HTTP_X_INERTIA="true").status_code
        == 403
    )


@pytest.mark.django_db
def test_scoped_actor_cannot_edit_out_of_boundary_resource(seeded_offices):
    actor = branch_admin()
    foreign = make(office("charlottesville-va"), "other-branch-doc")
    with pytest.raises(PermissionDenied):
        update_resource(
            actor,
            foreign.pk,
            cleaned={"title": "Hijacked"},
            expected_version=resource_version(foreign),
        )


@pytest.mark.django_db
def test_regional_admin_cannot_edit_company_owned_resource(seeded_offices):
    actor = regional_admin()
    company_resource = make(office("onest-head-office"), "company-handbook")
    with pytest.raises(PermissionDenied):
        update_resource(
            actor,
            company_resource.pk,
            cleaned={"title": "Hijacked company doc"},
            expected_version=resource_version(company_resource),
        )


@pytest.mark.django_db
def test_company_publish_permission_required_for_head_office(
    seeded_offices, monkeypatch
):
    # A company-wide actor WITHOUT the publish permission is still blocked.
    actor = completed_user(
        email="broker.admin@example.com", office=office("onest-head-office")
    )
    assign(
        actor, "principal_broker", "company"
    )  # protected role has _OPS_ALL… but no publish perm? it does.
    del actor
    limited = completed_user(
        email="limited.company@example.com", office=office("onest-head-office")
    )
    # Grant company-wide access without publish via a custom path: use the
    # service directly to prove publish permission is what gates head-office.
    from apps.user.services import office_resource_administration as svc

    class _StubAccess:
        company_wide = True
        region_keys = frozenset()
        office_keys = frozenset()

    monkeypatch.setattr(svc, "get_effective_access", lambda user: _StubAccess())
    assert not svc.can_publish_company(limited)
    with pytest.raises(PermissionDenied):
        svc.ensure_manage_authority(limited, office("onest-head-office"))


# ---------------------------------------------------------------------------
# Ownership + shadowing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_with_crafted_owner_is_blocked(seeded_offices):
    actor = branch_admin()
    crafted_owner = office("onest-head-office")
    with pytest.raises(PermissionDenied):
        create_resource(
            actor,
            cleaned={
                "owner_office": crafted_owner,
                "slug": "crafted",
                "title": "Crafted",
                "category": "general",
                "resource_type": "content",
                "body": "x",
                "is_active": False,
            },
        )


@pytest.mark.django_db
def test_scoped_actor_cannot_shadow_wider_scope_slug(seeded_offices):
    make(office("onest-head-office"), "wifi-password", body="Company default.")
    actor = branch_admin()
    with pytest.raises(ValidationError) as raised:
        create_resource(
            actor,
            cleaned={
                "owner_office": office("fairfax-va"),
                "slug": "wifi-password",
                "title": "Branch Wi-Fi",
                "category": "printer_wifi",
                "resource_type": "content",
                "body": "Branch override.",
            },
        )
    assert "shadow" in str(raised.value)


@pytest.mark.django_db
def test_company_actor_can_shadow_within_boundary(seeded_offices):
    make(office("region-mid-atlantic"), "wifi-password", body="Regional.")
    actor = company_admin()  # boundary includes everything
    resource = create_resource(
        actor,
        cleaned={
            "owner_office": office("onest-head-office"),
            "slug": "wifi-password",
            "title": "Company Wi-Fi",
            "category": "printer_wifi",
            "resource_type": "content",
            "body": "Company override.",
        },
    )
    assert resource.slug == "wifi-password"


# ---------------------------------------------------------------------------
# Optimistic concurrency
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_stale_version_rejected(seeded_offices):
    actor = branch_admin()
    resource = make(office("fairfax-va"), "concurrency-target")
    with pytest.raises(StaleResourceVersion):
        update_resource(
            actor,
            resource.pk,
            cleaned={"title": "Losing edit"},
            expected_version="stale-token",
        )


@pytest.mark.django_db
def test_concurrent_edits_first_write_wins(seeded_offices):
    actor = branch_admin()
    resource = make(office("fairfax-va"), "race-target")
    token = resource_version(resource)
    winner = update_resource(
        actor, resource.pk, cleaned={"title": "Winner"}, expected_version=token
    )
    with pytest.raises(StaleResourceVersion):
        update_resource(
            actor, resource.pk, cleaned={"title": "Loser"}, expected_version=token
        )
    resource.refresh_from_db()
    assert resource.title == "Winner"
    assert winner.title == "Winner"
    # Recoverable: reload → fresh token → second edit lands.
    fresh_token = resource_version(resource)
    update_resource(
        actor, resource.pk, cleaned={"title": "Recovered"}, expected_version=fresh_token
    )
    resource.refresh_from_db()
    assert resource.title == "Recovered"


# ---------------------------------------------------------------------------
# Server-side validation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_impossible_date_window_blocked(seeded_offices):
    from datetime import timedelta

    from django.utils import timezone

    actor = branch_admin()
    today = timezone.localdate()
    with pytest.raises(ValidationError):
        create_resource(
            actor,
            cleaned={
                "owner_office": office("fairfax-va"),
                "slug": "windowed",
                "title": "Windowed",
                "category": "general",
                "resource_type": "content",
                "body": "x",
                "starts_at": today,
                "ends_at": today - timedelta(days=1),
            },
        )


@pytest.mark.django_db
def test_non_https_link_blocked_via_form_and_service(seeded_offices):
    from apps.user.forms import OfficeResourceForm

    actor = branch_admin()
    form = OfficeResourceForm(
        {
            "owner_office": str(office("fairfax-va").pk),
            "slug": "insecure",
            "title": "Insecure link",
            "summary": "",
            "category": "vendor_contacts",
            "resource_type": "link",
            "body": "",
            "url": "http://insecure.example.com",
            "sort_order": "",
            "is_active": "on",
            "starts_at": "",
            "ends_at": "",
            "expected_version": "",
        },
        owner_queryset=Office.objects.filter(pk=office("fairfax-va").pk),
    )
    assert not form.is_valid()
    assert "url" in form.errors

    with pytest.raises(ValidationError):
        create_resource(
            actor,
            cleaned={
                "owner_office": office("fairfax-va"),
                "slug": "insecure",
                "title": "Insecure link",
                "category": "vendor_contacts",
                "resource_type": "link",
                "body": "",
                "url": "http://insecure.example.com",
            },
        )


# ---------------------------------------------------------------------------
# File lifecycle
# ---------------------------------------------------------------------------


def _upload(name: str, content: bytes):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, content)


@pytest.mark.django_db
def test_file_replace_updates_row_and_audits(seeded_offices, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    actor = branch_admin()
    resource = make(
        office("fairfax-va"),
        "forms-packet",
        resource_type="file",
        body="",
    )
    resource.file.save("old.pdf", ContentFile(b"old"), save=True)
    old_storage_name = resource.file.name

    updated = update_file(actor, resource, "new.pdf", b"new content")
    assert updated.original_file_name == "new.pdf"
    assert updated.processing_state == OfficeResource.ProcessingState.READY
    assert not updated.file.storage.exists(old_storage_name)
    assert AuditEvent.objects.filter(action="office_resource.file_replaced").exists()


def update_file(actor, resource, name: str, content: bytes):
    from apps.user.services.office_resource_administration import replace_file

    return replace_file(
        actor,
        resource.pk,
        uploaded_file=_upload(name, content),
        expected_version=resource_version(resource),
    )


@pytest.mark.django_db
def test_disallowed_extension_rejected(seeded_offices, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    actor = branch_admin()
    resource = make(office("fairfax-va"), "script-host", resource_type="file", body="")
    resource.file.save("safe.txt", ContentFile(b"x"), save=True)
    with pytest.raises(ValidationError):
        update_file(actor, resource, "evil.exe", b"MZ")


@pytest.mark.django_db
def test_oversized_file_rejected(seeded_offices, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    actor = branch_admin()
    resource = make(office("fairfax-va"), "big-file", resource_type="file", body="")
    resource.file.save("ok.txt", ContentFile(b"x"), save=True)
    from apps.user.services.office_resource_administration import MAX_FILE_BYTES

    with pytest.raises(ValidationError):
        update_file(actor, resource, "big.txt", b"a" * (MAX_FILE_BYTES + 1))


@pytest.mark.django_db
def test_quarantined_file_cannot_be_published(seeded_offices, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    actor = branch_admin()
    resource = make(
        office("fairfax-va"), "quarantine-me", resource_type="file", body=""
    )
    resource.file.save("good.txt", ContentFile(b"x"), save=True)

    from apps.user.services.office_resource_administration import replace_file

    with pytest.raises(ValidationError):
        replace_file(
            actor,
            resource.pk,
            uploaded_file=_upload("bad.exe", b"MZ"),
            expected_version=resource_version(resource),
        )
    resource.refresh_from_db()
    assert resource.is_active is False  # deactivated alongside quarantine
    # And activation stays blocked while quarantined.
    resource.is_active = True
    with pytest.raises(ValidationError):
        resource.full_clean(exclude={"created_by"})


# ---------------------------------------------------------------------------
# Archive lifecycle + cache invalidation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_archive_hides_from_agent_library_then_unarchive_restores(seeded_offices):
    from apps.user.services.office_resources import effective_library_for_office

    plain_agent()  # an agent exists but plays no part in admin transitions
    resource = make(office("fairfax-va"), "archivable")

    def library_slugs() -> set[str]:
        return {
            item.slug for item in effective_library_for_office(office("fairfax-va"))
        }

    assert "archivable" in library_slugs()

    admin = branch_admin()
    transition_resource(
        admin,
        resource.pk,
        action="archive",
        expected_version=resource_version(resource),
    )
    assert "archivable" not in library_slugs()
    assert AuditEvent.objects.filter(action="office_resource.archive").exists()

    resource.refresh_from_db()
    transition_resource(
        admin,
        resource.pk,
        action="unarchive",
        expected_version=resource_version(resource),
    )
    # Unarchive restores availability for editing; publishing needs activate.
    resource.refresh_from_db()
    transition_resource(
        admin,
        resource.pk,
        action="activate",
        expected_version=resource_version(resource),
    )
    assert "archivable" in library_slugs()


@pytest.mark.django_db
def test_cache_invalidation_after_save(seeded_offices):
    from apps.user.services.office_resources import (
        bump_generation,
        effective_library_for_office,
    )

    node = office("fairfax-va")
    first = effective_library_for_office(node)
    assert first == []
    make(node, "cached-in")
    second = effective_library_for_office(node)
    assert [item.slug for item in second] == ["cached-in"]
    bump_generation()


@pytest.mark.django_db
def test_move_up_moves_within_category(seeded_offices):
    actor = branch_admin()
    first = make(office("fairfax-va"), "a-first", category="shipping", sort_order=10)
    second = make(office("fairfax-va"), "b-second", category="shipping", sort_order=20)

    transition_resource(
        actor,
        second.pk,
        action="move_up",
        expected_version=resource_version(second),
    )
    first.refresh_from_db()
    second.refresh_from_db()
    assert second.sort_order == 10
    assert first.sort_order == 20
    assert AuditEvent.objects.filter(action="office_resource.move_up").exists()


# ---------------------------------------------------------------------------
# Preview + list payload
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_preview_matches_agent_library_with_origin_labels(seeded_offices):
    make(office("onest-head-office"), "company-handbook", body="Company copy.")
    make(office("fairfax-va"), "local-doc", body="Local copy.")

    actor = company_admin()
    payload = detail_payload(actor, None, preview_office_id=office("fairfax-va").pk)
    preview = payload["preview"]
    origins = {row["slug"]: row["origin"] for row in preview["items"]}
    assert origins["company-handbook"] == "inherited"
    assert origins["local-doc"] == "local"
    assert preview["localCount"] == 1
    assert preview["inheritedCount"] == 1

    # The preview must equal the user-facing effective library exactly.
    from apps.user.services.office_resources import effective_library_for_office

    agent_view = effective_library_for_office(office("fairfax-va"))
    assert {item.slug for item in agent_view} == set(origins)


@pytest.mark.django_db
def test_preview_rejects_out_of_scope_office(seeded_offices):
    actor = branch_admin()
    payload = detail_payload(
        actor, None, preview_office_id=office("charlottesville-va").pk
    )
    assert payload["preview"] is None


@pytest.mark.django_db
def test_list_filters_by_category_type_and_status(client, seeded_offices):
    actor = branch_admin()
    client.force_login(actor)
    make(office("fairfax-va"), "printer-doc", category="printer_wifi")
    make(office("fairfax-va"), "inactive-doc")
    OfficeResource.objects.filter(slug="inactive-doc").update(is_active=False)

    response = client.get(
        reverse("admin_office_resources"),
        {"category": "printer_wifi"},
        HTTP_X_INERTIA="true",
    )
    slugs = {row["slug"] for row in props(response)["resources"]["items"]}
    assert slugs == {"printer-doc"}

    response = client.get(
        reverse("admin_office_resources"),
        {"status": "inactive"},
        HTTP_X_INERTIA="true",
    )
    slugs = {row["slug"] for row in props(response)["resources"]["items"]}
    assert slugs == {"inactive-doc"}

    # Scope: another branch's resources never appear.
    make(office("charlottesville-va"), "foreign-doc")
    response = client.get(reverse("admin_office_resources"), HTTP_X_INERTIA="true")
    slugs = {row["slug"] for row in props(response)["resources"]["items"]}
    assert "foreign-doc" not in slugs


@pytest.mark.django_db
def test_managed_queryset_respects_scope(seeded_offices):
    actor = regional_admin()
    make(office("harrisburg"), "pa-doc")
    make(office("connecticut"), "ne-doc")
    keys = {item.slug for item in managed_resource_queryset(actor)}
    assert keys == {"pa-doc"}


# ---------------------------------------------------------------------------
# Create sheet (slide-over) error flow
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_sheet_create_failure_reopens_index_with_draft(client, seeded_offices):
    actor = branch_admin()
    client.force_login(actor)
    response = client.post(
        reverse("admin_office_resource_create"),
        {
            "context": "sheet",
            "title": "",  # required — fails validation
            "slug": "",
            "summary": "Draft summary",
            "category": "general",
            "resource_type": "content",
            "body": "x",
            "url": "",
            "owner_office": str(office("fairfax-va").pk),
            "sort_order": "",
            "starts_at": "",
            "ends_at": "",
            "is_active": "on",
        },
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 422
    payload = props(response)
    assert payload["createSheet"]["open"] is True
    assert payload["createSheet"]["draft"]["summary"] == "Draft summary"
    assert payload["createSheet"]["draft"].get("isActive") == "on"
    assert "title" in payload["validation"]["fields"]
    # The console still only shows in-scope rows alongside the errors.
    keys = {row["slug"] for row in payload["resources"]["items"]}
    assert keys == set()


@pytest.mark.django_db
def test_sheet_create_success_redirects_to_workspace(
    client, seeded_offices, settings, tmp_path
):
    settings.MEDIA_ROOT = str(tmp_path)
    actor = branch_admin()
    client.force_login(actor)
    response = client.post(
        reverse("admin_office_resource_create"),
        {
            "context": "sheet",
            "title": "Sheet made",
            "slug": "",
            "summary": "",
            "category": "general",
            "resource_type": "content",
            "body": "hello",
            "url": "",
            "owner_office": str(office("fairfax-va").pk),
            "sort_order": "5",
            "starts_at": "",
            "ends_at": "",
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    resource = OfficeResource.objects.get(slug="sheet-made")
    assert response.url == reverse("admin_office_resource", args=[resource.pk])


@pytest.mark.django_db
def test_workspace_get_pages_render_as_inertia(client, seeded_offices):
    """Both GET workspaces must return an Inertia page, not a bare dict."""
    actor = branch_admin()
    client.force_login(actor)
    resource = make(office("fairfax-va"), "workspace-doc")

    new_page = client.get(reverse("admin_office_resource_new"), HTTP_X_INERTIA="true")
    assert new_page.status_code == 200
    assert json.loads(new_page.content)["component"] == "OfficeResourceWorkspace"

    detail = client.get(
        reverse("admin_office_resource", args=[resource.pk]), HTTP_X_INERTIA="true"
    )
    assert detail.status_code == 200
    body = json.loads(detail.content)
    assert body["component"] == "OfficeResourceWorkspace"
    assert body["props"]["resource"]["slug"] == "workspace-doc"
