"""Widget composition layer: contracts, scope, timezone, failure, query cost."""

import json
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.user.models import Office, User
from apps.user.roles import BRANCH_MANAGER, ScopeType
from apps.web.dashboard import (
    WIDGET_BY_KEY,
    WIDGET_BY_PROP,
    WIDGET_DEFINITIONS,
    CachePolicy,
    CacheScope,
    WidgetStatus,
    build_context,
    deferred_widget_props,
    greeting_payload,
    load_widget,
    ready,
    unavailable,
    widget_cache_key,
    widget_payload,
)
from apps.web.dashboard.registry import _validate_registry
from apps.web.dashboard.timeframes import (
    end_of_local_day,
    first_name,
    salutation,
    start_of_local_day,
)
from apps.web.models import QuickAccessLink
from apps.web.quick_access.resolution import invalidate_configuration_cache
from apps.web.tests.test_dashboard_metrics import (
    assign,
    branch,
    make_user,
    other_region_office,
)


def inertia_props(response) -> dict:
    return json.loads(response.content)["props"]


def partial(client, user, prop: str) -> dict:
    client.force_login(user)
    response = client.get(
        reverse("dashboard"),
        HTTP_X_INERTIA="true",
        HTTP_X_INERTIA_PARTIAL_DATA=prop,
        HTTP_X_INERTIA_PARTIAL_COMPONENT="Dashboard",
    )
    assert response.status_code == 200
    return inertia_props(response)[prop]


def definitions_with(**providers):
    """Return registry rows with selected providers replaced by test doubles."""
    return tuple(
        replace(definition, provider=providers.get(definition.key, definition.provider))
        for definition in WIDGET_DEFINITIONS
    )


PRODUCTION_MIDDLEWARE = [
    middleware
    for middleware in settings.MIDDLEWARE
    if not middleware.startswith("silk.")
]


@contextmanager
def assert_application_queries(expected: int, *, ignore_tables: tuple[str, ...] = ()):
    """Count app SQL without Silk's order-dependent EXPLAIN statements.

    ``ignore_tables`` drops backend noise that varies by settings (e.g.
    ``django_session`` is skipped under ``cached_db`` after a warm request,
    but always counted under the plain ``db`` session engine).
    """
    with CaptureQueriesContext(connection) as captured:
        yield
    queries = []
    for query in captured.captured_queries:
        sql = query["sql"]
        if sql.lstrip().upper().startswith("EXPLAIN"):
            continue
        if any(f'"{table}"' in sql for table in ignore_tables):
            continue
        queries.append(sql)
    assert len(queries) == expected, "\n\n".join(queries)


@pytest.fixture(autouse=True)
def _clear_widget_cache():
    cache.clear()
    yield
    cache.clear()


# --------------------------------------------------------------------------- #
# Contract shape
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_every_widget_emits_the_full_envelope(client):
    user = make_user("envelope@example.com")
    context = build_context(user)
    for definition in WIDGET_DEFINITIONS:
        payload = widget_payload(definition, context)
        assert set(payload) == {
            "status",
            "version",
            "generatedAt",
            "data",
            "emptyState",
            "unavailable",
            "meta",
        }
        assert payload["status"] in {
            WidgetStatus.READY,
            WidgetStatus.EMPTY,
            WidgetStatus.UNAVAILABLE,
        }
        assert payload["version"] == definition.contract_version
        # A status always carries exactly the branch that explains it.
        if payload["status"] == WidgetStatus.READY:
            assert payload["data"] is not None
        if payload["status"] == WidgetStatus.EMPTY:
            assert payload["emptyState"]["title"]
        if payload["status"] == WidgetStatus.UNAVAILABLE:
            assert payload["unavailable"]["reason"]
            assert payload["data"] is None


def test_contract_versions_are_pinned():
    """A shape change must be a deliberate version bump, not a silent edit."""
    assert {
        definition.key: definition.contract_version for definition in WIDGET_DEFINITIONS
    } == {
        "performance": 1,
        "quick_access": 1,
        "announcements": 1,
        "active_transactions": 1,
        "training": 1,
        "my_day": 1,
        "action_items": 2,
        "market": 1,
        "quick_documents": 1,
    }


def test_registry_props_and_groups_are_unique_and_documented():
    assert len(WIDGET_BY_KEY) == len(WIDGET_DEFINITIONS)
    assert len(WIDGET_BY_PROP) == len(WIDGET_DEFINITIONS)
    for definition in WIDGET_DEFINITIONS:
        assert definition.group in {"metrics", "pipeline", "widgets"}
        assert definition.cache.rationale, f"{definition.key} needs a cache rationale"
        # Inertia props are camelCase by convention.
        assert "_" not in definition.prop


def test_registry_validation_rejects_a_shared_cache_on_user_data(monkeypatch):
    """The invariant that stops one agent's payload reaching another."""
    leaky = WIDGET_BY_KEY["announcements"]
    assert leaky.user_specific
    patched = tuple(
        (
            replace(
                leaky,
                cache=CachePolicy(
                    scope=CacheScope.SHARED, ttl_seconds=60, rationale="oops"
                ),
            )
            if definition.key == leaky.key
            else definition
        )
        for definition in WIDGET_DEFINITIONS
    )
    monkeypatch.setattr("apps.web.dashboard.registry.WIDGET_DEFINITIONS", patched)
    with pytest.raises(ValueError, match="cannot use a shared cache"):
        _validate_registry()


# --------------------------------------------------------------------------- #
# No fabricated data on production paths
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_no_widget_serves_placeholder_imagery_or_invented_records(client):
    user = make_user("no-fakes@example.com")
    client.force_login(user)
    response = client.get(reverse("dashboard"), HTTP_X_INERTIA="true")
    body = response.content.decode()
    assert "picsum.photos" not in body

    context = build_context(user)
    rendered = json.dumps(
        [widget_payload(definition, context) for definition in WIDGET_DEFINITIONS]
    )
    assert "picsum.photos" not in rendered
    # Sample records from the prototype.
    for invented in ("1842 Maple Ave", "$48,750", "6.73%", "Agent handbook"):
        assert invented not in rendered


@pytest.mark.django_db
def test_modules_without_a_backing_source_report_unavailable_not_empty():
    user = make_user("unbuilt@example.com")
    context = build_context(user)
    for key in (
        "announcements",
        "active_transactions",
        "training",
        "my_day",
        "market",
        "quick_documents",
    ):
        payload = widget_payload(WIDGET_BY_KEY[key], context)
        assert payload["status"] == WidgetStatus.UNAVAILABLE, key
        # Not retryable: asking again will not build the module.
        assert payload["unavailable"]["retryable"] is False, key


@pytest.mark.django_db
def test_quick_access_serves_administered_configuration():
    """The panel is data now — the migration's seed rows, not a code tuple."""
    user = make_user("tools@example.com")
    payload = widget_payload(WIDGET_BY_KEY["quick_access"], build_context(user))
    assert payload["status"] == WidgetStatus.READY
    assert [tool["id"] for tool in payload["data"]] == list(
        QuickAccessLink.objects.filter(
            is_active=True, is_archived=False, company_wide=True
        )
        .order_by("sort_order", "name", "pk")
        .values_list("stable_key", flat=True)
    )
    for tool in payload["data"]:
        assert tool["href"].startswith("https://")


# --------------------------------------------------------------------------- #
# Scope isolation
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_two_users_with_different_scope_get_different_payloads(client):
    home = branch(0)
    away = other_region_office(home)
    make_user("home-newbie@example.com", office=home)
    make_user("away-newbie@example.com", office=away)

    home_manager = make_user("home-mgr@example.com", office=home)
    assign(home_manager, BRANCH_MANAGER, ScopeType.OFFICE, home)
    away_manager = make_user("away-mgr@example.com", office=away)
    assign(away_manager, BRANCH_MANAGER, ScopeType.OFFICE, away)

    def new_agents(user) -> str:
        widget = partial(client, user, "metrics")
        return next(
            metric["value"]
            for group in widget["data"]["groups"]
            for metric in group["metrics"]
            if metric["key"] == "teamNewAgents"
        )

    # Each manager counts their own office's people, and nobody else's.
    assert new_agents(home_manager) == "2"
    assert new_agents(away_manager) == "2"

    home_widget = partial(client, home_manager, "metrics")
    away_widget = partial(client, away_manager, "metrics")
    assert home_widget["data"]["scope"]["label"] == home.name
    assert away_widget["data"]["scope"]["label"] == away.name
    assert home_widget["data"] != away_widget["data"]


@pytest.mark.django_db
def test_an_office_identifier_from_the_client_is_ignored(client):
    home = branch(0)
    away = other_region_office(home)
    make_user("scoped-away@example.com", office=away)
    manager = make_user("scoped-home@example.com", office=home)
    assign(manager, BRANCH_MANAGER, ScopeType.OFFICE, home)

    client.force_login(manager)
    response = client.get(
        reverse("dashboard"),
        {"office": Office.objects.get(pk=away.pk).stable_key, "user_id": "1"},
        HTTP_X_INERTIA="true",
        HTTP_X_INERTIA_PARTIAL_DATA="metrics",
        HTTP_X_INERTIA_PARTIAL_COMPONENT="Dashboard",
    )
    widget = inertia_props(response)["metrics"]
    assert widget["data"]["scope"]["label"] == home.name


# --------------------------------------------------------------------------- #
# Empty states
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_an_empty_account_gets_a_next_action_not_a_blank_card(client):
    widget = partial(client, make_user("brand-new@example.com"), "metrics")
    assert widget["status"] == WidgetStatus.EMPTY
    assert widget["emptyState"]["title"]
    assert widget["emptyState"]["description"]


@pytest.mark.django_db
def test_empty_state_can_carry_a_call_to_action():
    from apps.web.dashboard.envelope import empty

    result = empty(
        "Nothing yet",
        "Add your first record.",
        action_label="Add one",
        action_href="/hub/agent-transactions",
    )
    assert result.empty_state is not None
    payload = result.empty_state.payload()
    assert payload["actionLabel"] == "Add one"
    assert payload["actionHref"] == "/hub/agent-transactions"


# --------------------------------------------------------------------------- #
# Partial failure
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_failing_provider_does_not_break_the_shell_or_other_widgets(
    client, monkeypatch, caplog
):
    def explode(context):
        raise RuntimeError("SELECT secret FROM transactions WHERE owner_id = 42")

    broken = replace(WIDGET_BY_KEY["quick_access"], provider=explode)

    user = make_user("resilient@example.com")
    widget = load_widget(broken, build_context(user)).payload()

    assert widget["status"] == WidgetStatus.UNAVAILABLE
    # Retryable, because asking again might succeed.
    assert widget["unavailable"]["retryable"] is True
    # The reason must not leak the exception text to the browser.
    assert "SELECT" not in widget["unavailable"]["reason"]
    assert "42" not in widget["unavailable"]["reason"]


@pytest.mark.django_db
def test_a_failing_widget_still_returns_200_with_the_other_groups(client, monkeypatch):
    def explode(context):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "apps.web.dashboard.registry.WIDGET_DEFINITIONS",
        definitions_with(market=explode),
    )
    user = make_user("one-broken@example.com")
    client.force_login(user)
    response = client.get(reverse("dashboard"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    props = inertia_props(response)
    # The shell still painted, and the non-deferred greeting is intact.
    assert props["greeting"]["salutation"].startswith("Good ")

    broken = partial(client, user, "market")
    assert broken["status"] == WidgetStatus.UNAVAILABLE
    assert broken["unavailable"]["retryable"] is True

    healthy = partial(client, user, "quickApps")
    assert healthy["status"] == WidgetStatus.READY


@pytest.mark.django_db
def test_a_transient_failure_is_never_cached(monkeypatch):
    calls = {"count": 0}

    def flaky(context):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("transient")
        return ready([{"id": "lofty", "name": "Lofty", "href": "https://example.com"}])

    definition = replace(WIDGET_BY_KEY["quick_access"], provider=flaky)
    user = make_user("flaky@example.com")

    first = widget_payload(definition, build_context(user))
    assert first["status"] == WidgetStatus.UNAVAILABLE
    second = widget_payload(definition, build_context(user))
    assert second["status"] == WidgetStatus.READY


# --------------------------------------------------------------------------- #
# Caching
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_shared_cache_key_carries_no_user_identity():
    from apps.web.dashboard.registry import CachePolicy as Policy

    user = make_user("shared-key@example.com")
    shared = replace(
        WIDGET_BY_KEY["market"],
        cache=Policy(scope=CacheScope.SHARED, ttl_seconds=60, rationale="test"),
    )
    key = widget_cache_key(shared, build_context(user))
    assert key == "dashboard:market:1"


@pytest.mark.django_db
def test_the_quick_access_key_changes_when_configuration_changes():
    """A save must reach readers who already hold a cached panel."""
    user = make_user("config-key@example.com")
    definition = WIDGET_BY_KEY["quick_access"]
    before = widget_cache_key(definition, build_context(user))

    link = QuickAccessLink.objects.order_by("sort_order").first()
    assert link is not None
    link.name = f"{link.name} (renamed)"
    link.save()
    invalidate_configuration_cache()

    after = widget_cache_key(definition, build_context(user))
    assert before != after


@pytest.mark.django_db
def test_a_per_user_cache_key_changes_when_effective_access_changes():
    from apps.web.dashboard.registry import CachePolicy as Policy

    office = branch(0)
    user = make_user("per-user-key@example.com", office=office)
    definition = WIDGET_BY_KEY["announcements"]
    cached = replace(
        definition,
        cache=Policy(scope=CacheScope.PER_USER, ttl_seconds=60, rationale="test"),
    )

    before = widget_cache_key(cached, build_context(user))
    assign(user, BRANCH_MANAGER, ScopeType.OFFICE, office)
    after = widget_cache_key(cached, build_context(user))

    assert str(user.pk) in before.split(":")
    assert before != after, "granting a role must invalidate that user's widgets"


@pytest.mark.django_db
def test_a_cached_widget_is_computed_once_within_its_ttl(monkeypatch):
    calls = {"count": 0}

    def counted(context):
        calls["count"] += 1
        return ready([{"id": "a", "name": "A", "href": "https://example.com"}])

    definition = replace(WIDGET_BY_KEY["quick_access"], provider=counted)
    user = make_user("cached@example.com")

    widget_payload(definition, build_context(user))
    widget_payload(definition, build_context(user))
    assert calls["count"] == 1


@pytest.mark.django_db
def test_an_uncached_widget_is_recomputed_every_request(monkeypatch):
    calls = {"count": 0}

    def counted(context):
        calls["count"] += 1
        return unavailable("nope")

    definition = replace(WIDGET_BY_KEY["market"], provider=counted)
    user = make_user("uncached@example.com")
    widget_payload(definition, build_context(user))
    widget_payload(definition, build_context(user))
    assert calls["count"] == 2


# --------------------------------------------------------------------------- #
# Feed caps
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_list_payload_is_capped_at_the_registered_feed_limit(monkeypatch):
    definition = WIDGET_BY_KEY["quick_access"]
    oversized = [
        {"id": str(index), "name": str(index), "href": "https://example.com"}
        for index in range(definition.feed_limit + 5)
    ]
    definition = replace(definition, provider=lambda context: ready(oversized))
    payload = widget_payload(definition, build_context(make_user("feed@example.com")))
    assert len(payload["data"]) == definition.feed_limit
    assert payload["meta"]["truncated"] is True


@pytest.mark.django_db
def test_a_payload_inside_the_cap_is_not_marked_truncated():
    payload = widget_payload(
        WIDGET_BY_KEY["quick_access"], build_context(make_user("small@example.com"))
    )
    assert "truncated" not in payload["meta"]
    assert payload["status"] == WidgetStatus.READY


# --------------------------------------------------------------------------- #
# Timezone
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
@override_settings(TIME_ZONE="America/New_York")
def test_greeting_and_day_boundaries_use_the_application_timezone():
    timezone.activate("America/New_York")
    try:
        user = make_user("tz@example.com")
        # 03:30 UTC on 20 Aug is still 23:30 on 19 Aug in New York.
        at = datetime(2026, 8, 20, 3, 30, tzinfo=ZoneInfo("UTC"))

        payload = greeting_payload(user, at=at)
        assert payload["salutation"] == "Good evening"
        assert payload["dateIso"] == "2026-08-19"
        assert payload["timezone"] == "America/New_York"

        assert (
            start_of_local_day(user, at=at).isoformat() == "2026-08-19T00:00:00-04:00"
        )
        assert end_of_local_day(user, at=at).isoformat() == "2026-08-20T00:00:00-04:00"
    finally:
        timezone.deactivate()


@pytest.mark.django_db
@override_settings(TIME_ZONE="UTC")
def test_the_same_instant_reads_as_a_different_day_in_a_different_timezone():
    timezone.activate("UTC")
    try:
        user = make_user("tz-utc@example.com")
        at = datetime(2026, 8, 20, 3, 30, tzinfo=ZoneInfo("UTC"))
        assert greeting_payload(user, at=at)["dateIso"] == "2026-08-20"
    finally:
        timezone.deactivate()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (0, "Good morning"),
        (11, "Good morning"),
        (12, "Good afternoon"),
        (16, "Good afternoon"),
        (17, "Good evening"),
        (23, "Good evening"),
    ],
)
def test_salutation_boundaries(hour, expected):
    user = User(email="hours@example.com")
    at = timezone.make_aware(datetime(2026, 8, 19, hour, 0), ZoneInfo("UTC"))
    with override_settings(TIME_ZONE="UTC"):
        timezone.activate("UTC")
        try:
            assert salutation(user, at=at) == expected
        finally:
            timezone.deactivate()


def test_greeting_never_falls_back_to_an_email_address():
    assert first_name(User(email="alice@example.com", display_name="Alice Nguyen")) == (
        "Alice"
    )
    assert first_name(User(email="alice@example.com", first_name="Alice")) == "Alice"
    # Worst case is the local part, never the full address.
    assert first_name(User(email="alice@example.com")) == "alice"


@pytest.mark.django_db
def test_local_day_boundaries_span_exactly_one_day():
    user = make_user("span@example.com")
    at = timezone.now()
    assert end_of_local_day(user, at=at) - start_of_local_day(user, at=at) == timedelta(
        days=1
    )


# --------------------------------------------------------------------------- #
# Deferred delivery and query cost
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_the_first_load_defers_every_widget_and_ships_the_greeting(client):
    user = make_user("first-load@example.com")
    client.force_login(user)
    response = client.get(reverse("dashboard"), HTTP_X_INERTIA="true")
    data = json.loads(response.content)

    assert data["props"]["greeting"]["dateLabel"]
    for definition in WIDGET_DEFINITIONS:
        assert definition.prop not in data["props"], definition.prop
        assert definition.prop in data["deferredProps"][definition.group]


@pytest.mark.django_db
def test_widget_groups_arrive_independently(client):
    """A group's absence never blocks another group's delivery."""
    user = make_user("groups@example.com")
    client.force_login(user)
    for group in ("metrics", "pipeline", "widgets"):
        props = [
            definition.prop
            for definition in WIDGET_DEFINITIONS
            if definition.group == group
        ]
        response = client.get(
            reverse("dashboard"),
            HTTP_X_INERTIA="true",
            HTTP_X_INERTIA_PARTIAL_DATA=",".join(props),
            HTTP_X_INERTIA_PARTIAL_COMPONENT="Dashboard",
        )
        returned = inertia_props(response)
        assert all(prop in returned for prop in props)
        assert not any(
            definition.prop in returned
            for definition in WIDGET_DEFINITIONS
            if definition.group != group
        )


@pytest.mark.django_db
@override_settings(MIDDLEWARE=PRODUCTION_MIDDLEWARE)
def test_the_dashboard_shell_query_count_is_bounded(client):
    """The first paint must not scale with the number of widgets."""
    office = branch(0)
    user = make_user("shell-queries@example.com", office=office)
    assign(user, BRANCH_MANAGER, ScopeType.OFFICE, office)
    client.force_login(user)
    # Warm the session/user lookups so the assertion measures the page itself.
    client.get(reverse("dashboard"), HTTP_X_INERTIA="true")

    with assert_application_queries(7, ignore_tables=("django_session",)):
        client.get(reverse("dashboard"), HTTP_X_INERTIA="true")


@pytest.mark.django_db
def test_the_dashboard_shell_does_not_invoke_deferred_providers(client, monkeypatch):
    """A slow downstream provider cannot delay the first paint."""
    called: list[str] = []

    def should_stay_deferred(context):
        called.append("provider")
        return unavailable("spied")

    monkeypatch.setattr(
        "apps.web.dashboard.registry.WIDGET_DEFINITIONS",
        definitions_with(
            **{
                definition.key: should_stay_deferred
                for definition in WIDGET_DEFINITIONS
            }
        ),
    )
    user = make_user("deferred-shell@example.com")
    client.force_login(user)

    response = client.get(reverse("dashboard"), HTTP_X_INERTIA="true")

    assert response.status_code == 200
    assert called == []


@pytest.mark.django_db
def test_a_single_widget_reload_does_no_work_for_the_other_widgets(client, monkeypatch):
    """Partial reloads must not run every provider."""
    called: list[str] = []
    providers = {}
    for definition in WIDGET_DEFINITIONS:
        name = definition.key

        def spy(context, _name=name):
            called.append(_name)
            return unavailable("spied")

        providers[definition.key] = spy

    monkeypatch.setattr(
        "apps.web.dashboard.registry.WIDGET_DEFINITIONS",
        definitions_with(**providers),
    )

    user = make_user("one-provider@example.com")
    partial(client, user, "market")
    assert called == ["market"]


@pytest.mark.django_db
def test_widget_providers_are_bounded_in_queries():
    office = branch(0)
    user = make_user("widget-queries@example.com", office=office)
    assign(user, BRANCH_MANAGER, ScopeType.OFFICE, office)
    context = build_context(user)

    # The live provider reads one scoped count plus the scope's display name.
    with assert_application_queries(2):
        widget_payload(WIDGET_BY_KEY["performance"], context)

    # Providers awaiting their module must not touch the database at all.
    for key in ("announcements", "active_transactions", "market", "my_day"):
        with assert_application_queries(0):
            widget_payload(WIDGET_BY_KEY[key], context)

    # Quick access resolves the whole audience in one statement — the office
    # ancestor chain comes off the already-loaded user, and the configuration
    # stamp is cached — plus the read of the reader's own office row.
    cache.clear()
    with assert_application_queries(4):
        widget_payload(WIDGET_BY_KEY["quick_access"], context)


@pytest.mark.django_db
def test_the_composer_resolves_effective_access_once_per_response(client, monkeypatch):
    """Several widgets in one deferred response share one access lookup."""
    office = branch(0)
    user = make_user("one-access@example.com", office=office)
    assign(user, BRANCH_MANAGER, ScopeType.OFFICE, office)
    calls = {"count": 0}
    from apps.web.dashboard import registry

    real_get_effective_access = registry.get_effective_access

    def counted(current_user):
        calls["count"] += 1
        return real_get_effective_access(current_user)

    monkeypatch.setattr(registry, "get_effective_access", counted)
    client.force_login(user)
    response = client.get(
        reverse("dashboard"),
        HTTP_X_INERTIA="true",
        HTTP_X_INERTIA_PARTIAL_DATA="schedule,actionItems,market,documents",
        HTTP_X_INERTIA_PARTIAL_COMPONENT="Dashboard",
    )

    assert response.status_code == 200
    assert calls["count"] == 1


def test_deferred_props_cover_every_registered_widget():
    props = deferred_widget_props(User(email="props@example.com"))
    assert set(props) == {definition.prop for definition in WIDGET_DEFINITIONS}
