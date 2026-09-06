"""Load legacy onintra dump rows into Hub models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.announcements.models import (
    Announcement,
    AnnouncementAudience,
    AnnouncementCategory,
)
from apps.announcements.taxonomy import CATEGORY_SEED, PRIORITY_NORMAL
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.office_seed import SeedConflictError, seed_offices
from apps.user.onintra.mappings import (
    HEAD_OFFICE_SLUG,
    branch_slug,
    hub_role_code,
    infer_location_id,
    map_priority,
    map_tags_to_category,
    parse_mailing_address,
    region_slug,
    role_scope,
    split_display_name,
    state_office_slugs,
)
from apps.user.onintra.sql_dump import load_dump_tables
from apps.user.roles import (
    REALTOR,
    ScopeType,
    role_group_name,
    seed_brokerage_roles,
    seed_role_groups,
)

IMPORT_SECTIONS = ("users", "roles", "announcements")


@dataclass
class ImportReport:
    users_created: int = 0
    users_updated: int = 0
    users_skipped: int = 0
    assignments_created: int = 0
    assignments_matched: int = 0
    assignments_skipped: int = 0
    announcements_created: int = 0
    announcements_updated: int = 0
    announcements_skipped: int = 0
    audience_rows_created: int = 0
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            "onintra import: "
            f"users created={self.users_created}, updated={self.users_updated}, "
            f"skipped={self.users_skipped}; "
            f"assignments created={self.assignments_created}, "
            f"matched={self.assignments_matched}, skipped={self.assignments_skipped}; "
            f"announcements created={self.announcements_created}, "
            f"updated={self.announcements_updated}, "
            f"skipped={self.announcements_skipped}; "
            f"audience rows={self.audience_rows_created}; "
            f"warnings={len(self.warnings)}"
        )


def load_onintra_dump(
    *,
    dump_path: str | Path,
    dry_run: bool = False,
    skip_existing: bool = True,
    only: tuple[str, ...] | None = None,
) -> ImportReport:
    sections = _normalize_sections(only)
    tables = load_dump_tables(dump_path)
    report = ImportReport()

    with transaction.atomic():
        _ensure_prerequisites()
        legacy_user_ids: dict[int, User] = {}
        if "users" in sections:
            legacy_user_ids = _import_users(
                tables.get("users", []),
                report=report,
                skip_existing=skip_existing,
            )
        elif sections & {"roles", "announcements"}:
            legacy_user_ids = _index_users_by_legacy_id(tables.get("users", []))

        if "roles" in sections:
            _import_role_assignments(
                tables.get("user_roles", []),
                legacy_user_ids=legacy_user_ids,
                report=report,
            )

        if "announcements" in sections:
            _import_announcements(
                announcements=tables.get("announcements", []),
                visibilities=tables.get("announcement_visibilities", []),
                legacy_user_ids=legacy_user_ids,
                report=report,
                skip_existing=skip_existing,
            )

        if dry_run:
            transaction.set_rollback(True)

    return report


def _normalize_sections(only: tuple[str, ...] | None) -> frozenset[str]:
    if only is None:
        return frozenset(IMPORT_SECTIONS)
    unknown = sorted(set(only) - set(IMPORT_SECTIONS))
    if unknown:
        raise ValueError(
            f"Unknown import sections: {', '.join(unknown)}. "
            f"Choose from: {', '.join(IMPORT_SECTIONS)}."
        )
    return frozenset(only)


def _ensure_prerequisites() -> None:
    office_report = seed_offices()
    if office_report.conflicting:
        raise SeedConflictError(
            f"Office seed conflicts block import: {office_report.conflicting}"
        )
    seed_role_groups()
    seed_brokerage_roles()
    for item in CATEGORY_SEED:
        AnnouncementCategory.objects.update_or_create(
            code=item.code,
            defaults={"is_system": True},
            create_defaults={
                "code": item.code,
                "label": item.label,
                "description": item.description,
                "display_order": item.display_order,
                "is_active": True,
                "is_system": True,
            },
        )


def _import_users(
    rows: list[dict[str, Any]],
    *,
    report: ImportReport,
    skip_existing: bool,
) -> dict[int, User]:
    legacy_ids: dict[int, User] = {}
    for row in rows:
        legacy_id = _as_int(row.get("id"))
        email = str(row.get("email") or "").strip().lower()
        if legacy_id is None or not email:
            report.users_skipped += 1
            report.warnings.append(f"Skipped user id={legacy_id!r}: missing email.")
            continue

        existing = User.objects.filter(email=email).first()
        if existing is not None and skip_existing:
            legacy_ids[legacy_id] = existing
            report.users_skipped += 1
            continue

        first_name, last_name, display_name = split_display_name(
            str(row.get("name") or "")
        )
        address = parse_mailing_address(row.get("address"))
        license_expires_on = parse_date(str(row.get("license_expiration_date") or ""))
        defaults = {
            "first_name": first_name,
            "last_name": last_name,
            "display_name": display_name,
            "phone_number": _clean_phone(row.get("phone")),
            "street_address": address["street_address"],
            "city": address["city"],
            "state": address["state"],
            "zip_code": address["zip_code"],
            "license_number": str(row.get("license_id") or "").strip(),
            "license_expires_on": license_expires_on,
            "nrds_number": str(row.get("nrds_number") or "").strip(),
            "mls_number": str(row.get("mls_agent_id") or "").strip(),
            "bio": str(row.get("self_introduction") or "").strip(),
            "profile_completed": True,
            "profile_completed_at": timezone.now(),
            "is_active": True,
        }
        if existing is None:
            user = User(email=email, **defaults)
            user.set_unusable_password()
            user.save()
            report.users_created += 1
        else:
            User.objects.filter(pk=existing.pk).update(**defaults)
            user = User.objects.get(pk=existing.pk)
            report.users_updated += 1
        legacy_ids[legacy_id] = user
    return legacy_ids


def _index_users_by_legacy_id(rows: list[dict[str, Any]]) -> dict[int, User]:
    legacy_ids: dict[int, User] = {}
    for row in rows:
        legacy_id = _as_int(row.get("id"))
        email = str(row.get("email") or "").strip().lower()
        if legacy_id is None or not email:
            continue
        user = User.objects.filter(email=email).first()
        if user is not None:
            legacy_ids[legacy_id] = user
    return legacy_ids


def _import_role_assignments(
    rows: list[dict[str, Any]],
    *,
    legacy_user_ids: dict[int, User],
    report: ImportReport,
) -> None:
    offices = _office_lookup()
    realtor_branch_by_user: dict[int, int] = {}
    for row in rows:
        legacy_user_id = _as_int(row.get("id"))
        if _as_int(row.get("role_id")) != 7:
            continue
        branch_id = _as_int(row.get("location_id"))
        if legacy_user_id is not None and branch_id is not None:
            realtor_branch_by_user[legacy_user_id] = branch_id

    realtor_office_by_user: dict[int, str] = {}

    for row in rows:
        legacy_user_id = _as_int(row.get("id"))
        legacy_role_id = _as_int(row.get("role_id"))
        location_id = infer_location_id(
            legacy_role_id=legacy_role_id or -1,
            location_id=_as_int(row.get("location_id")),
            realtor_branch_id=realtor_branch_by_user.get(legacy_user_id or -1),
        )
        if legacy_user_id is None or legacy_role_id is None:
            report.assignments_skipped += 1
            continue

        user = legacy_user_ids.get(legacy_user_id)
        role_code = hub_role_code(legacy_role_id)
        if user is None:
            report.assignments_skipped += 1
            report.warnings.append(
                f"Skipped role assignment for legacy user id={legacy_user_id}: "
                "user not imported."
            )
            continue
        if role_code is None:
            report.assignments_skipped += 1
            report.warnings.append(
                f"Skipped unsupported legacy role_id={legacy_role_id} "
                f"for user {user.email}."
            )
            continue

        try:
            scope_type, scope_slug = role_scope(legacy_role_id, location_id)
        except KeyError as exc:
            report.assignments_skipped += 1
            report.warnings.append(
                f"Skipped role assignment for {user.email} ({role_code}): {exc}"
            )
            continue

        scope_office = offices.get(scope_slug) if scope_slug else None
        if scope_type in {ScopeType.REGION, ScopeType.OFFICE} and scope_office is None:
            report.assignments_skipped += 1
            report.warnings.append(
                f"Skipped role assignment for {user.email}: "
                f"office slug '{scope_slug}' is missing."
            )
            continue

        if role_code == REALTOR and scope_slug:
            realtor_office_by_user[legacy_user_id] = scope_slug

        existing = UserRoleAssignment.objects.filter(
            user=user,
            role=role_code,
            scope_type=scope_type,
            scope_office=scope_office,
            status__in=[
                UserRoleAssignment.Status.SCHEDULED,
                UserRoleAssignment.Status.ACTIVE,
            ],
        ).first()
        if existing is None:
            assignment = UserRoleAssignment(
                user=user,
                role=role_code,
                scope_type=scope_type,
                scope_office=scope_office,
            )
            assignment.refresh_status()
            assignment.full_clean()
            assignment.save()
            report.assignments_created += 1
        else:
            report.assignments_matched += 1

        group, _ = Group.objects.get_or_create(name=role_group_name(role_code))
        user.groups.add(group)

    for legacy_user_id, office_slug in realtor_office_by_user.items():
        user = legacy_user_ids.get(legacy_user_id)
        office = offices.get(office_slug)
        if user is None or office is None:
            continue
        if user.office is None or user.office.pk != office.pk:
            User.objects.filter(pk=user.pk).update(office=office)


def _import_announcements(
    *,
    announcements: list[dict[str, Any]],
    visibilities: list[dict[str, Any]],
    legacy_user_ids: dict[int, User],
    report: ImportReport,
    skip_existing: bool,
) -> None:
    offices = _office_lookup()
    head_office = offices[HEAD_OFFICE_SLUG]
    categories = {
        row.code: row for row in AnnouncementCategory.objects.filter(is_active=True)
    }
    visibilities_by_announcement: dict[int, list[dict[str, Any]]] = {}
    for row in visibilities:
        announcement_id = _as_int(row.get("announcement_id"))
        if announcement_id is None:
            continue
        visibilities_by_announcement.setdefault(announcement_id, []).append(row)

    for row in announcements:
        legacy_id = _as_int(row.get("id"))
        if legacy_id is None:
            report.announcements_skipped += 1
            continue

        slug = f"onintra-{legacy_id}"
        owner_slug = _infer_owner_office_slug(
            visibilities_by_announcement.get(legacy_id, [])
        )
        owner_office = offices.get(owner_slug, head_office)
        existing = Announcement.objects.filter(
            owner_office=owner_office,
            slug=slug,
        ).first()
        if existing is not None and skip_existing:
            report.announcements_skipped += 1
            continue

        created_by = legacy_user_ids.get(_as_int(row.get("created_by")) or -1)
        title = str(row.get("title") or "").strip() or f"Announcement {legacy_id}"
        summary = str(row.get("subject") or "").strip()
        body = str(row.get("content") or "").strip()
        category_code = map_tags_to_category(row.get("tags"))
        category = categories.get(category_code)
        if category is None:
            category = categories.get("company_announcement")
        priority = map_priority(row.get("priority"))
        status = _announcement_status(row)
        published_at = _aware(parse_datetime(str(row.get("published_at") or "")))
        expires_at = _aware(parse_datetime(str(row.get("expires_at") or "")))
        publish_at = published_at
        external_url = str(row.get("external_url") or "").strip()
        pinned = bool(int(row.get("pinned") or 0))

        defaults = {
            "title": title[:180],
            "summary": summary[:280],
            "body": body,
            "category": category,
            "priority": priority or PRIORITY_NORMAL,
            "status": status,
            "publish_at": publish_at,
            "expires_at": expires_at,
            "published_at": published_at
            if status == Announcement.Status.PUBLISHED
            else None,
            "is_pinned": pinned,
            "pinned_at": published_at if pinned else None,
            "cta_url": external_url[:500],
            "cta_label": "Open link" if external_url else "",
            "created_by": created_by,
            "updated_by": created_by,
        }

        if existing is None:
            announcement = Announcement.objects.create(
                owner_office=owner_office,
                slug=slug,
                **defaults,
            )
            report.announcements_created += 1
        else:
            Announcement.objects.filter(pk=existing.pk).update(**defaults)
            announcement = Announcement.objects.get(pk=existing.pk)
            AnnouncementAudience.objects.filter(announcement=existing).delete()
            report.announcements_updated += 1

        report.audience_rows_created += _create_audiences(
            announcement=announcement,
            visibility_rows=visibilities_by_announcement.get(legacy_id, []),
            legacy_user_ids=legacy_user_ids,
            offices=offices,
            report=report,
        )


def _create_audiences(
    *,
    announcement: Announcement,
    visibility_rows: list[dict[str, Any]],
    legacy_user_ids: dict[int, User],
    offices: dict[str, Office],
    report: ImportReport,
) -> int:
    if not visibility_rows:
        _, was_created = AnnouncementAudience.objects.get_or_create(
            announcement=announcement,
            kind=AnnouncementAudience.Kind.COMPANY,
        )
        return int(was_created)

    created = 0
    for row in visibility_rows:
        audience_type = str(row.get("audience_type") or "").strip().lower()
        audience_id = _as_int(row.get("audience_id"))

        if audience_type == "company":
            _, was_created = AnnouncementAudience.objects.get_or_create(
                announcement=announcement,
                kind=AnnouncementAudience.Kind.COMPANY,
            )
            created += int(was_created)
            continue

        if audience_type == "region":
            slug = region_slug(audience_id)
            office = offices.get(slug or "")
            if office is None:
                report.warnings.append(
                    f"Announcement {announcement.slug}: skipped legacy region "
                    f"audience id={audience_id}."
                )
                continue
            _, was_created = AnnouncementAudience.objects.get_or_create(
                announcement=announcement,
                kind=AnnouncementAudience.Kind.REGION,
                office=office,
            )
            created += int(was_created)
            continue

        if audience_type == "branch":
            slug = branch_slug(audience_id)
            office = offices.get(slug or "")
            if office is None:
                report.warnings.append(
                    f"Announcement {announcement.slug}: skipped legacy branch "
                    f"audience id={audience_id}."
                )
                continue
            _, was_created = AnnouncementAudience.objects.get_or_create(
                announcement=announcement,
                kind=AnnouncementAudience.Kind.OFFICE,
                office=office,
            )
            created += int(was_created)
            continue

        if audience_type == "agent":
            user = legacy_user_ids.get(audience_id or -1)
            if user is None:
                report.warnings.append(
                    f"Announcement {announcement.slug}: skipped legacy agent "
                    f"audience id={audience_id}."
                )
                continue
            _, was_created = AnnouncementAudience.objects.get_or_create(
                announcement=announcement,
                kind=AnnouncementAudience.Kind.USER,
                user=user,
            )
            created += int(was_created)
            continue

        if audience_type == "state":
            slugs = state_office_slugs(audience_id)
            if not slugs:
                report.warnings.append(
                    f"Announcement {announcement.slug}: legacy state audience "
                    f"id={audience_id} has no mapped Hub offices."
                )
                continue
            for slug in slugs:
                office = offices.get(slug)
                if office is None:
                    continue
                _, was_created = AnnouncementAudience.objects.get_or_create(
                    announcement=announcement,
                    kind=AnnouncementAudience.Kind.OFFICE,
                    office=office,
                )
                created += int(was_created)
            continue

        report.warnings.append(
            f"Announcement {announcement.slug}: unsupported audience type "
            f"'{audience_type}'."
        )
    return created


def _infer_owner_office_slug(visibility_rows: list[dict[str, Any]]) -> str:
    if not visibility_rows:
        return HEAD_OFFICE_SLUG

    types = {str(row.get("audience_type") or "").lower() for row in visibility_rows}
    if types == {"company"}:
        return HEAD_OFFICE_SLUG

    branch_ids = [
        _as_int(row.get("audience_id"))
        for row in visibility_rows
        if str(row.get("audience_type") or "").lower() == "branch"
        and _as_int(row.get("audience_id")) is not None
    ]
    if branch_ids and len({*branch_ids}) == 1:
        slug = branch_slug(branch_ids[0])
        if slug:
            return slug

    region_ids = [
        _as_int(row.get("audience_id"))
        for row in visibility_rows
        if str(row.get("audience_type") or "").lower() == "region"
        and _as_int(row.get("audience_id")) is not None
    ]
    if region_ids and len({*region_ids}) == 1:
        slug = region_slug(region_ids[0])
        if slug:
            return slug

    return HEAD_OFFICE_SLUG


def _announcement_status(row: dict[str, Any]) -> str:
    active = bool(int(row.get("active") or 0))
    expires_at = _aware(parse_datetime(str(row.get("expires_at") or "")))
    now = timezone.now()
    if not active:
        return Announcement.Status.ARCHIVED
    if expires_at is not None and expires_at <= now:
        return Announcement.Status.ARCHIVED
    published_at = _aware(parse_datetime(str(row.get("published_at") or "")))
    if published_at is None:
        return Announcement.Status.DRAFT
    return Announcement.Status.PUBLISHED


def _office_lookup() -> dict[str, Office]:
    return {office.slug: office for office in Office.objects.all()}


def _clean_phone(raw: Any) -> str:
    return str(raw or "").strip()[:30]


def _as_int(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    return int(raw)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value
