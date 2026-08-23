"""The registered search providers.

Each one starts from **its own domain's scoped queryset** and narrows from
there. None of them builds a scope filter of its own, and none reaches past the
function the domain already uses to serve its pages — that is the property that
keeps search from becoming the surface where authorization is re-implemented
slightly differently.

Sources named in the specification that are absent — documents, training,
transactions, CRM contacts, policies — have no model behind them yet. They are
deliberately not registered: a provider over a table that does not exist would
be a group heading that never returns anything, and inventing one to satisfy a
checklist is how a registry stops describing reality. They register in the
commit that ships their domain; ``test_search.py`` asserts every registered
provider's permission is catalogued and its route reverses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import reverse

from apps.web.search.contract import (
    SearchHit,
    SearchProvider,
    snippet_from,
)
from apps.web.search.ranking import search_ranked

if TYPE_CHECKING:
    from apps.user.models import User


# --------------------------------------------------------------------------- #
# People
# --------------------------------------------------------------------------- #


def search_people(actor: User, query: str, limit: int) -> list[SearchHit]:
    """The scoped people directory, searched by name and office.

    Two disclosure rules, both inherited rather than invented:

    * the row set is ``directory_queryset``, which is already office-scoped, so
      search cannot reach somebody the directory would not list; and
    * **email is only matched and shown when the actor may read it.** Matching
      on a field you cannot see turns search into an oracle — type an address,
      see whether a result appears — so the field is dropped from the predicate
      as well as from the snippet.
    """
    from apps.user.services.user_directory import (
        FieldGroup,
        directory_queryset,
        visible_field_groups,
    )

    groups = visible_field_groups(actor)
    may_read_contact = FieldGroup.ADMINISTRATION in groups

    # Names are matched by trigram on PostgreSQL rather than full text: there
    # is no document to rank, and the failure worth fixing is a half-remembered
    # spelling. ``search_ranked`` falls back to substring matching elsewhere.
    fields: tuple[str, ...] = (
        "first_name",
        "last_name",
        "display_name",
        "preferred_name",
        "office__name",
    )
    if may_read_contact:
        fields = (*fields, "email")

    rows = search_ranked(
        directory_queryset(actor).filter(is_active=True).select_related("office"),
        query,
        fields=fields,
        trigram_field="last_name",
        order=("first_name", "last_name"),
    )[:limit]
    return [
        SearchHit(
            id=str(row.pk),
            title=row.get_full_name() or row.display_name or "Unnamed",
            href=reverse("user_administration", args=[row.pk]),
            # Contact detail is a permitted field, not a free label: without
            # the administration grant the reader gets the office instead.
            snippet=row.email if may_read_contact else "",
            meta=row.office.name if row.office else "No office",
        )
        for row in rows
    ]


# --------------------------------------------------------------------------- #
# Announcements
# --------------------------------------------------------------------------- #


def search_announcements(actor: User, query: str, limit: int) -> list[SearchHit]:
    """Published, in-window announcements addressed to this reader.

    ``visible_announcements`` is the same predicate the feed, the detail page,
    and the attachment download use, so a draft, a scheduled notice, an expired
    one, or one addressed to another office cannot appear here — including in
    a snippet, which is why the body is only read from rows that survived it.
    """
    from apps.announcements.audience import visible_announcements

    rows = search_ranked(
        visible_announcements(actor),
        query,
        fields=("title", "summary", "body"),
        trigram_field="title",
        order=("-published_at",),
    )[:limit]
    return [
        SearchHit(
            id=str(row.pk),
            title=row.title,
            href=reverse("announcement_detail", args=[row.pk]),
            snippet=snippet_from(row.summary or row.body, query),
            meta=row.category.label if row.category else "Announcement",
        )
        for row in rows
    ]


# --------------------------------------------------------------------------- #
# Offices
# --------------------------------------------------------------------------- #


def search_offices(actor: User, query: str, limit: int) -> list[SearchHit]:
    """Active offices, by name or city.

    The office tree is brokerage-public: a name and a city are what the office
    directory shows every signed-in person. Nothing operational — access
    instructions, internal email, parking notes — is matched or projected, so
    this cannot be used to read an office's private half.
    """
    from apps.user.models import Office

    rows = search_ranked(
        Office.objects.filter(is_active=True).select_related("region"),
        query,
        fields=("name", "city"),
        trigram_field="name",
        order=("sort_order", "name"),
    )[:limit]
    return [
        SearchHit(
            id=str(row.pk),
            title=row.name,
            href=reverse("office_info"),
            snippet=row.city or "",
            meta=row.region.name if row.region else row.kind.replace("_", " ").title(),
        )
        for row in rows
    ]


# --------------------------------------------------------------------------- #
# Office resources
# --------------------------------------------------------------------------- #


def search_office_resources(actor: User, query: str, limit: int) -> list[SearchHit]:
    """The reader's own effective resource library.

    ``effective_resources_queryset`` already resolves the office scope chain and
    the closer-scope-wins precedence, so search shows exactly the library the
    resources page would. File bodies are never read: a protected file's *bytes*
    are behind an authorized download, and indexing them here would put their
    contents in a snippet that skips that check.
    """
    from apps.user.services.office_resources import effective_resources_queryset

    queryset = effective_resources_queryset(actor)
    if queryset is None:
        return []
    rows = search_ranked(
        queryset,
        query,
        fields=("title", "summary", "body"),
        trigram_field="title",
        order=("title",),
    )[:limit]
    return [
        SearchHit(
            id=str(row.pk),
            title=row.title,
            href=reverse("office_resources"),
            snippet=snippet_from(row.summary or row.body, query),
            meta=row.category.replace("_", " ").title() if row.category else "",
        )
        for row in rows
    ]


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #

SEARCH_PROVIDERS: tuple[SearchProvider, ...] = (
    SearchProvider(
        key="people",
        label="People",
        icon="users",
        search=search_people,
        permission="web.view_users",
        order=10,
        all_results_route="admin_users",
    ),
    SearchProvider(
        key="announcements",
        label="Announcements",
        icon="megaphone",
        search=search_announcements,
        # No capability gate: everybody may search the news addressed to them,
        # and the audience predicate is what decides what that is.
        permission="",
        order=20,
        all_results_route="announcements",
    ),
    SearchProvider(
        key="office-resources",
        label="Office resources",
        icon="folder",
        search=search_office_resources,
        permission="",
        order=30,
        all_results_route="office_resources",
    ),
    SearchProvider(
        key="offices",
        label="Offices",
        icon="building",
        search=search_offices,
        permission="",
        order=40,
        all_results_route="office_info",
    ),
)

SEARCH_PROVIDERS_BY_KEY: dict[str, SearchProvider] = {
    provider.key: provider for provider in SEARCH_PROVIDERS
}
