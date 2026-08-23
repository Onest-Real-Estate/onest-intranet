"""Relevance ranking, with one implementation per database that has one.

Two paths, chosen from the live connection rather than from a setting:

* **PostgreSQL** — real full-text search. A ``tsvector`` over the projected
  fields, matched with ``websearch_to_tsquery`` so an author can type
  ``"office closed" -training`` and mean it, ranked with ``ts_rank``, and
  widened by trigram similarity so ``fairfx`` still finds Fairfax.
* **Anything else** — the substring match this replaced. The test suite runs on
  SQLite, which has neither ``tsvector`` nor ``pg_trgm``, so the fallback is
  not dead code: it is the path CI exercises, and it has to keep returning the
  same rows in the same order.

Why the vendor check and not a setting
--------------------------------------
A setting can disagree with the database it is pointed at. ``connection.vendor``
cannot. The consequence of getting it wrong is a 500 on every search, so it is
worth reading the truth rather than a copy of it.

Ordering is total on both paths
-------------------------------
Rank first, then a stable identity tiebreak. Two rows of equal relevance would
otherwise come back in whatever order the database felt like, which is how the
same row appears on page one and page two of the same result set. Every caller
here depends on that not happening — see ``docs/search.md``.
"""

from __future__ import annotations

from typing import Any

from django.db import connection
from django.db.models import F, Q, QuerySet
from django.db.models.functions import Greatest

#: PostgreSQL's own default for ``pg_trgm.similarity_threshold``, recorded here
#: for the docs and the diagnostics payload. The filter uses the ``%`` operator
#: rather than a comparison against this number, because ``%`` is what the
#: trigram index can answer; change the behaviour by setting the GUC, not by
#: editing this constant.
TRIGRAM_THRESHOLD = 0.3

#: Field weights, strongest first. Postgres understands four labels; a title hit
#: should outrank a body hit for the same term, which is the whole reason to
#: weight rather than concatenate.
WEIGHT_TITLE = "A"
WEIGHT_SUMMARY = "B"
WEIGHT_BODY = "C"


def supports_full_text() -> bool:
    """Whether this connection can do ``tsvector`` work at all."""
    return connection.vendor == "postgresql"


def _fallback(queryset: QuerySet, query: str, *, fields: tuple[str, ...]) -> QuerySet:
    """Substring matching, ordered deterministically.

    No relevance to speak of — every match is equal — so the order is the
    caller's own, made total with the primary key.
    """
    predicate = Q()
    for field in fields:
        predicate |= Q(**{f"{field}__icontains": query})
    return queryset.filter(predicate)


def search_ranked(
    queryset: QuerySet,
    query: str,
    *,
    fields: tuple[str, ...],
    trigram_field: str | None = None,
    order: tuple[str, ...] = (),
) -> QuerySet:
    """Match and rank ``queryset`` against ``query``.

    ``fields`` are ranked by position: the first gets weight A, the second B,
    everything after C. ``trigram_field`` is the one field worth fuzzy-matching
    — a title or a name — because trigram similarity over a long body is both
    slow and meaningless.

    The queryset handed in is already scoped by its domain. This only ever
    *narrows* it: there is no path here that adds a row, which is what lets
    search reuse a domain's authorization instead of restating it.
    """
    if not supports_full_text():
        return _fallback(queryset, query, fields=fields).order_by(*order, "pk")

    from django.contrib.postgres.search import (
        SearchQuery,
        SearchRank,
        SearchVector,
        TrigramSimilarity,
    )

    weights = [WEIGHT_TITLE, WEIGHT_SUMMARY]
    parts = [
        SearchVector(
            field,
            weight=weights[index] if index < len(weights) else WEIGHT_BODY,
            config="english",
        )
        for index, field in enumerate(fields)
    ]
    vector = parts[0]
    for part in parts[1:]:
        vector = vector + part

    # ``websearch`` rather than ``plain``: it accepts quoted phrases and a
    # leading ``-`` for exclusion, and — unlike ``raw`` — it cannot raise on a
    # malformed query, so a stray operator is treated as text instead of a 500.
    search_query = SearchQuery(query, config="english", search_type="websearch")

    # The *filter* is what an index can answer, and the two available operators
    # are the only ones that qualify:
    #
    #   ``vector @@ query``            → the GIN full-text index
    #   ``field % 'text'``             → the GIN trigram index
    #
    # ``ts_rank(...) > 0`` and ``similarity(...) > 0.25`` express the same
    # intent and are *not* index-usable: PostgreSQL has to compute them for
    # every row, so an index built for them is never chosen. Ranking functions
    # therefore appear only in ``ORDER BY``, over rows the operators already
    # narrowed.
    annotated = queryset.annotate(search=vector, rank=SearchRank(vector, search_query))
    predicate = Q(search=search_query)

    if trigram_field:
        annotated = annotated.annotate(
            similarity=TrigramSimilarity(trigram_field, query)
        )
        # ``__trigram_similar`` compiles to ``%``, which the trigram index
        # answers. Its cut-off is PostgreSQL's own
        # ``pg_trgm.similarity_threshold`` rather than a number chosen here —
        # see TRIGRAM_THRESHOLD.
        predicate |= Q(**{f"{trigram_field}__trigram_similar": query})
        annotated = annotated.annotate(relevance=Greatest("rank", "similarity"))
        ordering: tuple[str, ...] = ("-relevance",)
    else:
        annotated = annotated.annotate(relevance=F("rank"))
        ordering = ("-relevance",)

    return annotated.filter(predicate).order_by(*ordering, *order, "pk")


def ranking_debug() -> dict[str, Any]:
    """What the current connection can do, for the search page's diagnostics."""
    return {
        "vendor": connection.vendor,
        "fullText": supports_full_text(),
        "trigramThreshold": TRIGRAM_THRESHOLD,
    }


__all__ = [
    "TRIGRAM_THRESHOLD",
    "ranking_debug",
    "search_ranked",
    "supports_full_text",
]
