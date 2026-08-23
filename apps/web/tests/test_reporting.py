"""Operational reporting framework: registry, scope, reconciliation, exports."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.http import Http404
from django.utils import timezone

from apps.user.models import User
from apps.web.metrics import SOURCE_MODULE_AVAILABILITY
from apps.web.models import ReportExportJob
from apps.web.reporting.exports import (
    create_export_job,
    download_export,
    export_job_payload,
    mark_expired_exports,
    process_export_job,
    render_export_bytes,
)
from apps.web.reporting.filters import parse_report_filters
from apps.web.reporting.registry import (
    REPORT_BY_KEY,
    REPORT_DEFINITIONS,
    run_report,
    select_reports,
)
from apps.web.reporting.service import report_catalog_payload, report_page_payload
from apps.web.tests.test_dashboard_metrics import (
    agent,
    branch,
    branch_manager,
    make_user,
    other_region_office,
)


def grant(user: User, *codenames: str) -> None:
    for codename in codenames:
        app_label, name = codename.split(".", 1)
        permission = Permission.objects.get(
            content_type__app_label=app_label, codename=name
        )
        user.user_permissions.add(permission)


@pytest.mark.django_db
def test_registry_keys_are_unique_and_documented():
    keys = [definition.key for definition in REPORT_DEFINITIONS]
    assert len(keys) == len(set(keys))
    for definition in REPORT_DEFINITIONS:
        assert definition.definition.strip()
        assert definition.source_module in SOURCE_MODULE_AVAILABILITY


@pytest.mark.django_db
def test_select_reports_requires_permissions_and_scope():
    home = branch()
    realtor = agent("agent-rpt@example.com", home)
    grant(realtor, "web.view_reports", "web.view_own_transactions")

    keys = {definition.key for definition in select_reports(realtor)}
    assert "agentBookOfBusiness" in keys
    assert "onboardingProgress" not in keys

    manager = branch_manager("manager-rpt@example.com", home)
    grant(
        manager,
        "web.view_reports",
        "web.view_new_agents",
        "web.view_users",
        "web.view_own_transactions",
    )
    manager_keys = {definition.key for definition in select_reports(manager)}
    assert "onboardingProgress" in manager_keys
    assert "officeHeadcount" in manager_keys


@pytest.mark.django_db
def test_onboarding_aggregates_reconcile_with_rows():
    home = branch()
    outsider = other_region_office(home)
    manager = branch_manager("mgr-onboard@example.com", home)
    grant(manager, "web.view_reports", "web.view_new_agents")

    for index in range(3):
        person = make_user(f"new-{index}@example.com", office=home)
        person.profile_completed = False
        person.save(update_fields=["profile_completed"])
    leak = make_user("leak@example.com", office=outsider)
    leak.profile_completed = False
    leak.save(update_fields=["profile_completed"])

    definition = REPORT_BY_KEY["onboardingProgress"]
    _context, result, _columns = run_report(manager, definition)
    assert result.aggregates["total"] == len(result.rows)
    assert sum(point.value for point in result.series) == result.aggregates["total"]
    assert all(row.get("office") == home.name for row in result.rows)
    assert all(row.get("office") != outsider.name for row in result.rows)


@pytest.mark.django_db
def test_office_filter_outside_scope_returns_empty():
    home = branch()
    outsider = other_region_office(home)
    manager = branch_manager("mgr-scope@example.com", home)
    grant(manager, "web.view_reports", "web.view_users")
    make_user("inside@example.com", office=home)
    make_user("outside@example.com", office=outsider)

    definition = REPORT_BY_KEY["officeHeadcount"]
    _context, result, _columns = run_report(
        manager, definition, filters={"office": outsider.stable_key}
    )
    assert result.aggregates["total"] == 0
    assert result.rows == ()


@pytest.mark.django_db
def test_rejected_filters_are_dropped():
    definition = REPORT_BY_KEY["onboardingProgress"]
    accepted, rejected = parse_report_filters(
        definition.filters,
        {"status": "not_a_real_status", "office": "ok-office", "hack": "1"},
    )
    assert "status" in rejected
    assert "hack" in rejected
    assert accepted.get("office") == "ok-office"


@pytest.mark.django_db
def test_export_projects_same_columns_and_is_idempotent(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    home = branch()
    manager = branch_manager("mgr-export@example.com", home)
    grant(
        manager,
        "web.view_reports",
        "web.export_reports",
        "web.view_users",
    )
    make_user("person@example.com", office=home)

    first = create_export_job(
        manager, "officeHeadcount", filters={}, export_format="csv"
    )
    second = create_export_job(
        manager, "officeHeadcount", filters={}, export_format="csv"
    )
    assert first.pk == second.pk

    process_export_job(first.pk)
    first.refresh_from_db()
    assert first.status == ReportExportJob.Status.READY
    content, _content_type, meta = render_export_bytes(
        manager, "officeHeadcount", filters={}, export_format="csv"
    )
    body = content.decode("utf-8")
    assert "name," in body.splitlines()[1]
    assert meta["columnKeys"] == ["name", "email", "office", "accountState"]


@pytest.mark.django_db
def test_expired_export_deletes_file_and_404s(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    home = branch()
    manager = branch_manager("mgr-expire@example.com", home)
    grant(
        manager,
        "web.view_reports",
        "web.export_reports",
        "web.view_users",
    )
    job = create_export_job(manager, "officeHeadcount")
    process_export_job(job.pk)
    job.refresh_from_db()
    job.expires_at = timezone.now() - timedelta(minutes=1)
    job.save(update_fields=["expires_at"])
    assert mark_expired_exports() == 1
    job.refresh_from_db()
    assert job.status == ReportExportJob.Status.EXPIRED
    assert not job.file
    with pytest.raises(Http404):
        download_export(manager, job.pk)


@pytest.mark.django_db
def test_catalog_and_detail_payloads():
    home = branch()
    manager = branch_manager("mgr-page@example.com", home)
    grant(
        manager,
        "web.view_reports",
        "web.view_new_agents",
        "web.view_users",
        "web.export_reports",
    )
    catalog = report_catalog_payload(manager)
    assert any(item["key"] == "onboardingProgress" for item in catalog["reports"])
    detail = report_page_payload(manager, "onboardingProgress", params={})
    assert detail["report"]["key"] == "onboardingProgress"
    assert "columns" in detail["report"]


@pytest.mark.django_db
def test_pending_source_module_is_marked_unavailable():
    home = branch()
    manager = branch_manager("mgr-pending@example.com", home)
    grant(manager, "web.view_reports", "web.view_transactions")
    definition = REPORT_BY_KEY["officePerformance"]
    assert SOURCE_MODULE_AVAILABILITY[definition.source_module] is False
    _context, result, _columns = run_report(manager, definition)
    assert result.empty_reason
    assert result.rows == ()


@pytest.mark.django_db
def test_sync_row_limit_truncates_interactive_not_export():
    home = branch()
    manager = branch_manager("mgr-limit@example.com", home)
    grant(manager, "web.view_reports", "web.view_users", "web.export_reports")
    for index in range(5):
        make_user(f"limit-{index}@example.com", office=home)

    definition = REPORT_BY_KEY["officeHeadcount"]
    _ctx, bounded, _ = run_report(manager, definition, row_limit=2)
    assert len(bounded.rows) == 2
    assert bounded.aggregates["truncated"] is True

    _ctx, full, _ = run_report(manager, definition, unbounded=True)
    assert len(full.rows) >= 5
    assert full.aggregates["truncated"] is False

    content, _ctype, meta = render_export_bytes(
        manager, "officeHeadcount", filters={}, export_format="csv"
    )
    # Header + one data line per person (at least the five seeded users).
    data_lines = [
        line
        for line in content.decode("utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    assert len(data_lines) - 1 >= 5  # minus CSV header
    assert meta["columnKeys"] == ["name", "email", "office", "accountState"]


@pytest.mark.django_db
def test_export_failure_is_observable(monkeypatch, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    home = branch()
    manager = branch_manager("mgr-fail@example.com", home)
    grant(manager, "web.view_reports", "web.export_reports", "web.view_users")
    job = create_export_job(manager, "officeHeadcount")

    def boom(*_args, **_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(
        "apps.web.reporting.exports.render_export_bytes",
        boom,
    )
    assert process_export_job(job.pk) == "failed"
    job.refresh_from_db()
    assert job.status == ReportExportJob.Status.FAILED
    assert "disk full" in job.error_message
    payload = export_job_payload(job)
    assert payload["status"] == "failed"
    assert payload["errorMessage"] == job.error_message
    assert payload["downloadReady"] is False


@pytest.mark.django_db
def test_detail_denies_without_domain_permission():
    home = branch()
    actor = agent("denied-rpt@example.com", home)
    grant(actor, "web.view_reports")
    with pytest.raises(PermissionError):
        report_page_payload(actor, "onboardingProgress", params={})
