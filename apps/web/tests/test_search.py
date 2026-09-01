"""Global search: what each reader finds, and what they cannot learn exists.

The assertions are deliberately about *absence*. A search result set is a
description of the records somebody may reach, so a leak here is not a wrong
row on a page — it is a way to enumerate the brokerage a keystroke at a time.
Several tests therefore check that a hidden record contributes no hit, no
snippet, no count, and no group heading.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.urls import reverse

from apps.announcements.models import Announcement, AnnouncementAudience
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.tests.test_profile import completed_user
from apps.web.search.contract import (
    MAX_QUERY_LENGTH,
    MIN_QUERY_LENGTH,
    is_searchable,
    normalize_query,
    snippet_from,
)
from apps.web.search.providers import SEARCH_PROVIDERS, SEARCH_PROVIDERS_BY_KEY
from apps.web.search.service import (
    RATE_LIMIT_REQUESTS,
    RateLimited,
    check_rate_limit,
    permitted_providers,
    run_search,
)


@pytest.fixture(autouse=True)
def clear_rate_limit():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def grant(user: User, *codenames: str) -> User:
    for codename in codenames:
        app_label, _, name = codename.partition(".")
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=name)
        )
    return User.objects.get(pk=user.pk)


def assign(user, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def reader(email="reader@example.com", slug="fairfax-va") -> User:
    existing = User.objects.filter(email=email).first()
    return existing or completed_user(email=email, office=office(slug))


def group(payload, key: str) -> dict | None:
    return next((g for g in payload["groups"] if g["key"] == key), None)


def require_group(payload, key: str) -> dict:
    """``group`` for assertions that have already established it is there."""
    found = group(payload, key)
    assert found is not None, f"expected a {key} group"
    return found


def titles(payload, key: str) -> list[str]:
    found = group(payload, key)
    return [hit["title"] for hit in found["hits"]] if found else []


def announcement(
    slug: str, *, owner="onest-head-office", body="", audience_office=None
):
    from apps.announcements.models import AnnouncementCategory

    row = Announcement(
        owner_office=office(owner),
        slug=slug,
        title=slug.replace("-", " ").title(),
        summary="",
        body=body,
        category=AnnouncementCategory.objects.get(code="company_announcement"),
        priority="normal",
        status=Announcement.Status.PUBLISHED,
    )
    from django.utils import timezone

    row.published_at = timezone.now()
    row.full_clean()
    row.save()
    AnnouncementAudience.objects.create(
        announcement=row,
        kind=(
            AnnouncementAudience.Kind.OFFICE
            if audience_office
            else AnnouncementAudience.Kind.COMPANY
        ),
        office=office(audience_office) if audience_office else None,
    )
    return row


# --------------------------------------------------------------------------- #
# Query normalization
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Fairfax   VA ", "Fairfax VA"),
        ("\tFairfax\nVA", "Fairfax VA"),
        ("Fairfax VA", "Fairfax VA"),
        (None, ""),
        ("", ""),
    ],
)
def test_queries_normalize_to_one_canonical_form(raw, expected):
    """Same query, same results, same order, same rate-limit key."""
    assert normalize_query(raw) == expected


def test_a_pasted_essay_is_truncated_rather_than_refused():
    assert len(normalize_query("x" * 5000)) == MAX_QUERY_LENGTH


def test_a_query_below_the_minimum_is_not_searched():
    assert is_searchable("a") is False
    assert is_searchable("ab") is True


def test_a_short_query_returns_no_groups_and_says_why(seeded):
    payload = run_search(reader(), "a")

    assert payload["groups"] == []
    assert payload["tooShort"] is True
    assert payload["minLength"] == MIN_QUERY_LENGTH


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #


def test_provider_keys_are_unique():
    assert len(SEARCH_PROVIDERS_BY_KEY) == len(SEARCH_PROVIDERS)


def test_every_provider_permission_is_in_the_reviewed_catalog():
    from apps.web.permission_catalog import CATALOG_CODENAMES

    unknown = {
        provider.permission
        for provider in SEARCH_PROVIDERS
        if provider.permission and provider.permission not in CATALOG_CODENAMES
    }
    assert unknown == set()


def test_every_all_results_route_reverses(seeded):
    for provider in SEARCH_PROVIDERS:
        if provider.all_results_route:
            reverse(provider.all_results_route)


# --------------------------------------------------------------------------- #
# Capability gating
# --------------------------------------------------------------------------- #


def test_an_anonymous_visitor_searches_nothing(seeded):
    from django.contrib.auth.models import AnonymousUser

    assert permitted_providers(AnonymousUser()) == []
    assert run_search(AnonymousUser(), "fairfax")["groups"] == []


def test_a_source_the_reader_may_not_use_is_never_named(seeded):
    """Absent, not empty: "no results in People" still discloses a People."""
    payload = run_search(reader(), "fairfax")

    assert group(payload, "people") is None
    assert "People" not in json.dumps(payload)


def test_granting_the_permission_admits_the_source(seeded):
    user = grant(reader("dir@example.com"), "web.view_users")
    assign(user, "regional_admin", "region", office("region-mid-atlantic"))

    payload = run_search(User.objects.get(pk=user.pk), "fairfax")

    assert group(payload, "people") is not None


# --------------------------------------------------------------------------- #
# Scope: the domain decides, not the aggregator
# --------------------------------------------------------------------------- #


def test_people_results_stop_at_the_directory_scope(seeded):
    """Search cannot reach somebody the directory itself would not list."""
    completed_user(email="inscope.person@example.com", office=office("fairfax-va"))
    completed_user(email="outscope.person@example.com", office=office("connecticut"))
    branch_admin = grant(reader("branch@example.com"), "web.view_users")
    assign(branch_admin, "branch_admin", "office", office("fairfax-va"))

    payload = run_search(User.objects.get(pk=branch_admin.pk), "person")
    serialized = json.dumps(payload)

    assert "outscope.person@example.com" not in serialized
    assert "outscope" not in serialized


def test_an_announcement_for_another_office_contributes_nothing(seeded):
    """Not a hit, not a snippet, not a count — the record must be unlearnable."""
    announcement(
        "harrisburg-only",
        body="SECRETWORD confidential to Harrisburg",
        audience_office="harrisburg",
    )

    payload = run_search(reader(), "SECRETWORD")
    # The query itself is echoed back, so only the *results* are searched for
    # the leak — asserting on the whole payload would always find the needle.
    serialized = json.dumps(payload["groups"])

    assert payload["total"] == 0
    assert "SECRETWORD" not in serialized
    assert "harrisburg-only" not in serialized


def test_a_draft_announcement_is_not_searchable(seeded):
    row = announcement("live-notice", body="visible words")
    draft = announcement("draft-notice", body="SECRETDRAFT words")
    draft.status = Announcement.Status.DRAFT
    draft.published_at = None
    draft.save(update_fields=["status", "published_at"])

    payload = run_search(reader(), "words")

    assert titles(payload, "announcements") == [row.title]
    assert "SECRETDRAFT" not in json.dumps(payload)


def test_an_expired_announcement_leaves_search_with_the_feed(seeded):
    from datetime import timedelta

    from django.utils import timezone

    row = announcement("expired-notice", body="SECRETEXPIRED words")
    row.expires_at = timezone.now() - timedelta(days=1)
    row.save(update_fields=["expires_at"])

    payload = run_search(reader(), "SECRETEXPIRED")

    assert payload["total"] == 0
    assert "SECRETEXPIRED" not in json.dumps(payload["groups"])


# --------------------------------------------------------------------------- #
# Field-level disclosure
# --------------------------------------------------------------------------- #


def test_email_is_neither_matched_nor_shown_without_the_grant(seeded):
    """Matching a field you cannot read turns search into an oracle."""
    completed_user(email="hidden.address@example.com", office=office("fairfax-va"))
    # Transaction Coordinator is the reviewed bundle that lists people without
    # carrying ``user.view_user_administration`` — the real shape of "may find
    # somebody, may not read their contact details".
    plain = grant(reader("plain@example.com"), "web.view_users")
    assign(plain, "transaction_coordinator", "office", office("fairfax-va"))
    plain = User.objects.get(pk=plain.pk)
    from apps.user.services.user_directory import FieldGroup, visible_field_groups

    assert FieldGroup.ADMINISTRATION not in visible_field_groups(plain)

    by_email = run_search(plain, "hidden.address")
    serialized = json.dumps(run_search(plain, "hidden"))

    assert titles(by_email, "people") == []
    assert "hidden.address@example.com" not in serialized


def test_email_is_matched_and_shown_with_the_administration_grant(seeded):
    completed_user(email="findable.address@example.com", office=office("fairfax-va"))
    admin = grant(
        reader("admin@example.com"),
        "web.view_users",
        "user.view_user_administration",
    )
    assign(admin, "regional_admin", "region", office("region-mid-atlantic"))

    payload = run_search(User.objects.get(pk=admin.pk), "findable.address")

    assert titles(payload, "people")


# --------------------------------------------------------------------------- #
# Snippets
# --------------------------------------------------------------------------- #


def test_a_snippet_is_plain_text_with_no_markup_to_sanitize():
    """Highlighting is a client-side match, so nothing here can inject."""
    window = snippet_from("Before <script>alert(1)</script> after", "script")

    assert "<script>alert(1)</script>" in window
    assert window == " ".join(window.split())


def test_a_snippet_windows_around_the_match_rather_than_truncating_the_head():
    body = "padding " * 40 + "NEEDLE " + "tail " * 40
    window = snippet_from(body, "NEEDLE")

    assert "NEEDLE" in window
    assert window.startswith("…")


def test_a_snippet_of_an_empty_body_is_empty_not_an_ellipsis():
    assert snippet_from("", "x") == ""
    assert snippet_from(None, "x") == ""


# --------------------------------------------------------------------------- #
# Isolation, caps, and budget
# --------------------------------------------------------------------------- #


def _with_broken(monkeypatch, key: str) -> None:
    """Swap one provider for a failing copy.

    ``SearchProvider`` is frozen, so the substitution builds a replacement and
    hands the aggregator a modified provider list — which also proves the
    isolation is in ``run_search`` rather than in any single provider.
    """
    import dataclasses

    def explode(actor, query, limit):
        raise RuntimeError(f"{key} is down")

    replacements = [
        dataclasses.replace(provider, search=explode)
        if provider.key == key
        else provider
        for provider in SEARCH_PROVIDERS
    ]
    monkeypatch.setattr(
        "apps.web.search.service.permitted_providers",
        lambda actor: [
            provider for provider in replacements if not provider.permission
        ],
    )


def test_one_failing_provider_does_not_empty_the_response(seeded, monkeypatch):
    announcement("stable-notice", body="findable words")
    _with_broken(monkeypatch, "offices")

    payload = run_search(reader(), "findable")

    assert payload["partial"] is True
    assert require_group(payload, "offices")["failed"] is True
    # The healthy source still answered.
    assert titles(payload, "announcements")


def test_a_failing_provider_is_reported_rather_than_silently_dropped(
    seeded, monkeypatch
):
    _with_broken(monkeypatch, "offices")

    payload = run_search(reader(), "fairfax")

    assert group(payload, "offices") is not None
    assert require_group(payload, "offices")["failed"] is True


def test_each_provider_respects_its_cap_and_reports_truncation(seeded):
    for index in range(9):
        announcement(f"capped-notice-{index}", body="cappable words")

    payload = run_search(reader(), "cappable")
    announcements = require_group(payload, "announcements")

    assert len(announcements["hits"]) == SEARCH_PROVIDERS_BY_KEY["announcements"].cap
    assert announcements["truncated"] is True
    assert announcements["allResultsHref"].endswith("?q=cappable")


def test_an_exhausted_budget_skips_the_rest_and_says_so(seeded):
    payload = run_search(reader(), "fairfax", budget=-1)

    assert payload["partial"] is True
    assert all(entry["failed"] for entry in payload["groups"])
    assert payload["total"] == 0


def test_the_group_order_is_stable_across_runs(seeded):
    user = grant(reader("stable@example.com"), "web.view_users")
    assign(user, "system_admin", "company")
    announcement("orderable-notice", body="orderable words")
    resolved = User.objects.get(pk=user.pk)

    first = [entry["key"] for entry in run_search(resolved, "orderable")["groups"]]
    second = [entry["key"] for entry in run_search(resolved, "orderable")["groups"]]

    assert first == second


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #


def test_the_window_allows_ordinary_typing_then_refuses_a_sweep(seeded):
    user = reader("limited@example.com")
    for _ in range(RATE_LIMIT_REQUESTS):
        check_rate_limit(user)

    with pytest.raises(RateLimited):
        check_rate_limit(user)


def test_the_window_forgives_once_it_has_passed(seeded):
    user = reader("forgiven@example.com")
    for index in range(RATE_LIMIT_REQUESTS):
        check_rate_limit(user, now=float(index))

    # Far enough ahead that every earlier stamp has aged out.
    check_rate_limit(user, now=10_000.0)


def test_one_actor_cannot_spend_anothers_allowance(seeded):
    first = reader("first@example.com")
    second = reader("second@example.com", "harrisburg")
    for _ in range(RATE_LIMIT_REQUESTS):
        check_rate_limit(first)

    check_rate_limit(second)


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #


def test_the_suggestions_endpoint_answers_json_for_a_signed_in_reader(seeded, client):
    announcement("http-notice", body="httpsearchable words")
    client.force_login(reader())

    response = client.get(reverse("search_suggestions"), {"q": "httpsearchable"})

    assert response.status_code == 200
    assert titles(response.json(), "announcements")


def test_the_suggestions_endpoint_refuses_an_anonymous_caller(seeded, client):
    response = client.get(reverse("search_suggestions"), {"q": "fairfax"})

    assert response.status_code == 401


def test_the_suggestions_endpoint_rate_limits_with_429(seeded, client):
    client.force_login(reader())
    for _ in range(RATE_LIMIT_REQUESTS):
        client.get(reverse("search_suggestions"), {"q": "fairfax"})

    response = client.get(reverse("search_suggestions"), {"q": "fairfax"})

    assert response.status_code == 429
    assert response.json()["error"] == "rate_limited"


def test_the_full_page_is_not_rate_limited(seeded, client):
    """One navigation, not a keystroke — following "see all" must never 429."""
    client.force_login(reader())
    for _ in range(RATE_LIMIT_REQUESTS + 5):
        response = client.get(reverse("search"), {"q": "fairfax"})

    assert response.status_code == 200


def test_the_full_page_returns_the_same_authorized_set(seeded, client):
    announcement("page-notice", body="pagesearchable words")
    client.force_login(reader())

    response = client.get(
        reverse("search"), {"q": "pagesearchable"}, HTTP_X_INERTIA="true"
    )
    props = json.loads(response.content.decode())["props"]

    assert titles(props["results"], "announcements")
    assert group(props["results"], "people") is None


def test_a_result_destination_re_enforces_its_own_access(seeded, client):
    """Search hands out a link; the link is still a door with its own lock."""
    admin = grant(
        reader("linker@example.com"),
        "web.view_users",
        "user.view_user_administration",
    )
    assign(admin, "system_admin", "company")
    subject = completed_user(email="subject@example.com", office=office("fairfax-va"))

    client.force_login(User.objects.get(pk=admin.pk))
    payload = run_search(User.objects.get(pk=admin.pk), "subject")
    href = require_group(payload, "people")["hits"][0]["href"]

    # The same URL, followed by somebody who may not open it.
    client.force_login(reader("nosy@example.com", "harrisburg"))
    assert client.get(href).status_code in {403, 404}
    assert subject.pk


def test_the_query_count_is_bounded_by_the_provider_set(
    seeded, django_assert_num_queries
):
    """Search must cost a fixed number of queries, not one per result."""
    for index in range(6):
        announcement(f"counted-{index}", body="countable words")
    user = reader("counter@example.com")

    # Warm the access lookup so the assertion measures the providers.
    run_search(user, "warmup")
    with django_assert_num_queries(8):
        run_search(user, "countable")


# --------------------------------------------------------------------------- #
# Ranking: two backends, one contract
# --------------------------------------------------------------------------- #


def test_the_ranking_path_is_chosen_from_the_live_connection(seeded):
    """A setting can disagree with the database; ``connection.vendor`` cannot."""
    from django.db import connection

    from apps.web.search.ranking import ranking_debug, supports_full_text

    assert supports_full_text() is (connection.vendor == "postgresql")
    assert ranking_debug()["vendor"] == connection.vendor


def test_matching_returns_the_same_rows_on_whichever_backend(seeded):
    """The fallback is not dead code — it is the path CI runs."""
    from apps.web.search.ranking import search_ranked

    announcement("ranked-alpha", body="distinctive marker text")
    announcement("ranked-beta", body="nothing relevant here")

    rows = search_ranked(
        Announcement.objects.all(),
        "distinctive",
        fields=("title", "summary", "body"),
        trigram_field="title",
        order=("-published_at",),
    )

    assert [row.slug for row in rows] == ["ranked-alpha"]


def test_the_order_is_total_so_equal_rows_never_swap(seeded):
    """Two rows of equal relevance must not come back in a different order on
    a second query — that is how a row appears on two pages of one result set."""
    from apps.web.search.ranking import search_ranked

    for index in range(5):
        announcement(f"tied-{index}", body="identical body text")

    def run():
        return [
            row.slug
            for row in search_ranked(
                Announcement.objects.all(),
                "identical",
                fields=("title", "summary", "body"),
                trigram_field="title",
            )
        ]

    assert run() == run()


def test_ranking_only_narrows_the_queryset_it_was_given(seeded):
    """The scope guarantee: no path here can add a row a domain withheld."""
    from apps.web.search.ranking import search_ranked

    announcement("in-scope-notice", body="shared word")
    announcement("withheld-notice", body="shared word")
    scoped = Announcement.objects.filter(slug="in-scope-notice")

    rows = search_ranked(
        scoped, "shared", fields=("title", "summary", "body"), trigram_field="title"
    )

    assert [row.slug for row in rows] == ["in-scope-notice"]


def test_a_query_full_of_operators_does_not_raise(seeded):
    """``websearch`` treats a stray operator as text; ``raw`` would 500."""
    from apps.web.search.ranking import search_ranked

    announcement("operator-notice", body="ordinary words")

    for hostile in ['"unclosed', "-", "&|!()", "a & b", "'; DROP TABLE x; --"]:
        rows = search_ranked(
            Announcement.objects.all(),
            hostile,
            fields=("title", "summary", "body"),
            trigram_field="title",
        )
        assert list(rows) is not None


def test_a_hostile_query_cannot_reach_the_database_as_sql(seeded, client):
    """End to end: injection-shaped input is a query string, never SQL."""
    announcement("safe-notice", body="ordinary words")
    client.force_login(reader())

    response = client.get(
        reverse("search_suggestions"), {"q": "'; DROP TABLE user_user; --"}
    )

    assert response.status_code == 200
    # The table is still there, which is the assertion that matters.
    assert User.objects.exists()


def test_the_index_migrations_are_a_no_op_away_from_postgres(seeded):
    """They must not fail on SQLite, and must not enter migration state."""
    from django.db import connection
    from django.db.migrations.loader import MigrationLoader

    from apps.web.search.operations import AddIndexIfPostgres

    loader = MigrationLoader(connection)
    migration = loader.disk_migrations[
        ("announcements", "0008_announcement_search_indexes")
    ]
    index_ops = [
        operation
        for operation in migration.operations
        if isinstance(operation, AddIndexIfPostgres)
    ]

    assert index_ops
    # State is untouched, which is why ``makemigrations --check`` stays clean
    # on a backend where the index does not exist.
    before = {}
    for operation in index_ops:
        operation.state_forwards("announcements", before)
    assert before == {}
