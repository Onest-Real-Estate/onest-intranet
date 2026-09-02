from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from apps.announcements.models import Announcement, AnnouncementAudience
from apps.user.models import User, UserRoleAssignment
from apps.user.onintra.loader import load_onintra_dump
from apps.user.onintra.mappings import (
    map_priority,
    map_tags_to_category,
    parse_mailing_address,
    role_scope,
    split_display_name,
)
from apps.user.onintra.sql_dump import load_dump_tables
from apps.user.roles import REALTOR, ScopeType

SAMPLE_SQL = textwrap.dedent(
    """
    INSERT INTO `users` (`id`, `name`, `email`, `password`, `phone`, `address`,
    `license_id`, `license_expiration_date`, `nrds_number`, `mls_agent_id`,
    `self_introduction`, `created_at`, `updated_at`) VALUES
    (1, 'Ada Lovelace', 'ada@onest.realestate', 'hash', '555 0100',
    '1 Main St Mechanicsburg PA 17055', 'LIC-1', '2028-01-01', '12345678',
    '999', 'Bio text', '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
    (2, 'Grace Hopper', 'grace@onest.realestate', 'hash', NULL, NULL,
    NULL, NULL, NULL, NULL, NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00');

    INSERT INTO `user_roles` (`sl`, `id`, `role_id`, `location_id`, `created_at`,
    `updated_at`) VALUES
    (1, 1, 7, 4, '2026-01-01 00:00:00', '2026-01-01 00:00:00'),
    (2, 2, 2, NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00');

    INSERT INTO `announcements` (`id`, `created_by`, `title`, `subject`, `content`,
    `featured_image_url`, `external_url`, `external_preview`, `tags`, `priority`,
    `pinned`, `views`, `published_at`, `expires_at`, `active`, `created_at`,
    `updated_at`) VALUES
    (10, 1, 'Fairfax Notice', 'Subject line', 'Body copy', NULL,
    'https://example.com', NULL, '["Training"]', 'high', 0, 0,
    '2026-06-01 12:00:00', NULL, 1, '2026-06-01 12:00:00', '2026-06-01 12:00:00');

    INSERT INTO `announcement_visibilities` (`id`, `announcement_id`, `audience_type`,
    `audience_id`, `created_at`, `updated_at`) VALUES
    (1, 10, 'branch', 4, '2026-06-01 12:00:00', '2026-06-01 12:00:00');
    """
)


def test_sql_dump_parser_reads_insert_rows(tmp_path: Path):
    dump_path = tmp_path / "sample.sql"
    dump_path.write_text(SAMPLE_SQL, encoding="utf-8")

    tables = load_dump_tables(dump_path)

    assert len(tables["users"]) == 2
    assert tables["users"][0]["email"] == "ada@onest.realestate"
    assert tables["users"][0]["name"] == "Ada Lovelace"
    assert tables["user_roles"][0]["role_id"] == 7
    assert tables["announcements"][0]["priority"] == "high"


def test_mapping_helpers():
    assert split_display_name("Ada Lovelace") == ("Ada", "Lovelace", "Ada Lovelace")
    assert map_priority("high") == "important"
    assert map_tags_to_category('["Webinars"]') == "training_notice"
    assert role_scope(7, 4) == (ScopeType.OFFICE, "fairfax-va")
    assert role_scope(2, None) == (ScopeType.COMPANY, None)
    parsed = parse_mailing_address("1 Main St, Mechanicsburg PA 17055")
    assert parsed["city"] == "Mechanicsburg"
    assert parsed["state"] == "PA"


@pytest.mark.django_db
def test_load_onintra_dump_imports_sample_rows(tmp_path: Path):
    dump_path = tmp_path / "sample.sql"
    dump_path.write_text(SAMPLE_SQL, encoding="utf-8")

    report = load_onintra_dump(dump_path=dump_path, skip_existing=False)

    ada = User.objects.get(email="ada@onest.realestate")
    assert ada.display_name == "Ada Lovelace"
    assert ada.license_number == "LIC-1"
    assert ada.bio == "Bio text"

    realtor_assignment = UserRoleAssignment.objects.select_related("scope_office").get(
        user=ada, role=REALTOR
    )
    assert realtor_assignment.scope_type == ScopeType.OFFICE
    scope_office = realtor_assignment.scope_office
    assert scope_office is not None
    assert scope_office.slug == "fairfax-va"
    ada_office = ada.office
    assert ada_office is not None
    assert ada_office.slug == "fairfax-va"

    announcement = Announcement.objects.get(slug="onintra-10")
    assert announcement.title == "Fairfax Notice"
    assert announcement.priority == "important"
    assert announcement.status == Announcement.Status.PUBLISHED
    assert AnnouncementAudience.objects.filter(
        announcement=announcement,
        kind=AnnouncementAudience.Kind.OFFICE,
        office__slug="fairfax-va",
    ).exists()
    assert report.users_created == 2
    assert report.assignments_created == 2
    assert report.announcements_created == 1


@pytest.mark.django_db
def test_load_onintra_dump_dry_run_rolls_back(tmp_path: Path):
    dump_path = tmp_path / "sample.sql"
    dump_path.write_text(SAMPLE_SQL, encoding="utf-8")

    load_onintra_dump(dump_path=dump_path, dry_run=True)

    assert not User.objects.filter(email="ada@onest.realestate").exists()
    assert not Announcement.objects.filter(slug="onintra-10").exists()
