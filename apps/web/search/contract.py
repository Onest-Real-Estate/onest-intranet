"""The search provider contract.

One rule shapes this whole module: **the aggregator never queries a domain.**
It asks a provider, and every provider starts from its own domain's already-
scoped queryset — ``visible_announcements`` for news, ``directory_queryset`` for
people, ``effective_resources_queryset`` for office resources. Search is
therefore exactly as permissive as the pages those functions already serve, and
a scope fix in a domain reaches search without anybody remembering to mirror it.

The alternative — a central index the aggregator filters itself — is how search
becomes the one surface that leaks. It would need its own copy of every
domain's rules, and that copy would drift.

What a provider must promise
----------------------------
* **Authorization is the domain's**, applied before anything is projected.
* **Titles and snippets are plain text.** No HTML crosses this boundary, so
  there is no markup to sanitize and no highlight to escape. Highlighting is a
  client-side match against the plain string.
* **Only fields the actor may read.** A snippet is a disclosure: a directory
  reader who may not see notes must not meet them in a search result.
* **A cap.** Every provider returns at most ``cap`` hits, so one busy domain
  cannot crowd out the rest or make the response unbounded.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

#: Nothing shorter is searched. A one-character query against scoped querysets
#: is enumeration dressed as search, and it matches most of the brokerage.
MIN_QUERY_LENGTH = 2

#: Longest query accepted. Anything past this is truncated rather than refused —
#: a paste is a mistake, not an attack, and refusing it loses what was typed.
MAX_QUERY_LENGTH = 120

#: Default hits per provider. Deliberately small: the dialog groups results and
#: offers "see all", so depth belongs on the full page, not in the popover.
DEFAULT_CAP = 5


@dataclass(frozen=True)
class SearchHit:
    """One result, already projected to what this actor may read.

    ``href`` is built by the provider from a typed route reverse. ``snippet``
    and ``title`` are plain text — never markup — and ``meta`` is the one line
    of context that tells two similarly-named results apart.
    """

    id: str
    title: str
    href: str
    snippet: str = ""
    meta: str = ""
    #: Lower sorts first inside a provider's own group. Providers that have no
    #: meaningful ranking leave it at zero and rely on their queryset order.
    rank: int = 0

    def payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "href": self.href,
            "snippet": self.snippet,
            "meta": self.meta,
        }


@dataclass(frozen=True)
class SearchProvider:
    """One searchable domain.

    ``permission`` is a capability gate applied *before* the provider runs, so
    an unauthorized source is never even asked — its label does not appear, and
    a failure in it cannot disclose that it exists. ``""`` means any
    authenticated reader may search it, with the domain's own scoping still
    doing the real work (announcements are the example: everybody may search
    them, and the audience predicate decides what that means).
    """

    key: str
    label: str
    icon: str
    #: ``(actor, query, limit) -> Sequence[SearchHit]``. Must start from the
    #: domain's own scoped queryset.
    search: Callable[..., Sequence[SearchHit]]
    permission: str = ""
    cap: int = DEFAULT_CAP
    order: int = 100
    #: Route name for "see all N results in this source", reversed with
    #: ``?q=``. Empty when the domain has no list page to send anybody to.
    all_results_route: str = ""
    all_results_query: str = "q"


@dataclass
class ProviderResult:
    """What one provider returned, or how it failed.

    A failure is recorded rather than raised: one domain being down must not
    empty the whole result set, and the reader is told which source is missing
    instead of being shown a shorter list that looks complete.
    """

    key: str
    label: str
    icon: str
    hits: list[SearchHit] = field(default_factory=list)
    failed: bool = False
    truncated: bool = False
    all_results_href: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "icon": self.icon,
            "hits": [hit.payload() for hit in self.hits],
            "failed": self.failed,
            "truncated": self.truncated,
            "allResultsHref": self.all_results_href,
        }


def normalize_query(raw: str | None) -> str:
    """Collapse whitespace, trim, and bound the length.

    Normalizing here rather than in each provider is what makes ranking stable:
    ``"  Fairfax   VA "`` and ``"Fairfax VA"`` are the same query, so they
    produce the same results in the same order and the same cache key for rate
    limiting.
    """
    if not raw:
        return ""
    return " ".join(raw.split())[:MAX_QUERY_LENGTH]


def is_searchable(query: str) -> bool:
    return len(query) >= MIN_QUERY_LENGTH


def snippet_from(text: str | None, query: str, *, width: int = 120) -> str:
    """A plain-text window around the first match.

    Returns text, never markup: the client highlights by matching the same
    query against this string, so there is no HTML to sanitize and no way for
    a record's own content to inject anything into the page.
    """
    body = " ".join((text or "").split())
    if not body:
        return ""
    lowered = body.lower()
    position = lowered.find(query.lower())
    if position == -1:
        return body[:width] + ("…" if len(body) > width else "")
    start = max(0, position - width // 3)
    end = min(len(body), start + width)
    window = body[start:end]
    return f"{'…' if start > 0 else ''}{window}{'…' if end < len(body) else ''}"
