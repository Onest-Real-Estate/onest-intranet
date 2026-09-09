"""Source registry and the composer the unified view calls.

Each domain registers a collector returning :class:`ReservationSummary` rows for
the signed-in user. A collector that raises is logged and skipped, so one broken
module cannot blank the page — the reader still sees every source that answered,
plus an honest note naming the one that did not.

The composer reads. It never writes, and it never calls a domain's lifecycle
service: actions carry their own source endpoints.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from apps.web.my_reservations.contract import (
    RESERVATION_BUCKETS,
    ReservationBucket,
    ReservationSource,
    ReservationSummary,
    bucket_for,
)

logger = logging.getLogger(__name__)

ReservationCollector = Callable[..., list[ReservationSummary]]


@dataclass(frozen=True)
class ReservationSourceDefinition:
    key: str
    collector: ReservationCollector | None = None
    #: False while a module is registered but not yet connected. The collector
    #: is not called, so nothing can be fabricated on its behalf.
    available: bool = False


def _collect_rooms(user, *, now):
    # Imported lazily so this registry does not pull either app graph during
    # unrelated startup paths.
    from apps.reservations.summaries import collect_room_reservations

    return collect_room_reservations(user, now=now)


def _collect_inventory(user, *, now):
    from apps.inventory.summaries import collect_inventory_reservations

    return collect_inventory_reservations(user, now=now)


RESERVATION_SOURCE_DEFINITIONS: tuple[ReservationSourceDefinition, ...] = (
    ReservationSourceDefinition(
        key=ReservationSource.ROOM, collector=_collect_rooms, available=True
    ),
    ReservationSourceDefinition(
        key=ReservationSource.INVENTORY, collector=_collect_inventory, available=True
    ),
)


@dataclass(frozen=True)
class ReservationFeed:
    """What the view renders: rows the reader may see, and what went missing."""

    summaries: tuple[ReservationSummary, ...]
    #: Sources that raised. Named so the page can say which half is incomplete
    #: rather than silently presenting a partial list as the whole truth.
    failed_sources: tuple[str, ...]
    counts: dict[str, int]

    @property
    def is_degraded(self) -> bool:
        return bool(self.failed_sources)


def _sort_key(summary: ReservationSummary, *, bucket: str) -> tuple[int, float, str]:
    """Deterministic order, with a stable tiebreak so paging cannot drift.

    Upcoming reads soonest-first — the next thing you must do. Past and
    cancelled read newest-first, because recency is what a reader looks back
    for. ``source_id`` breaks ties so two rows starting in the same minute
    always land in the same order, which is what makes a cursor stable.

    The position is a signed timestamp rather than a datetime: one list holds
    every bucket, and mixing a datetime key with a "time until" key would make
    the two incomparable.
    """
    stamp = summary.starts_at.timestamp()
    ascending = bucket == ReservationBucket.UPCOMING
    return (
        RESERVATION_BUCKETS.index(bucket),
        stamp if ascending else -stamp,
        summary.source_id,
    )


def collect_reservations(user, *, now: datetime | None = None) -> ReservationFeed:
    """Every reservation belonging to ``user``, from every available source.

    There is no owner parameter by design. A self-service surface that accepted
    one would be one missing check away from serving somebody else's calendar.
    """
    moment = now or timezone.now()
    rows: list[ReservationSummary] = []
    failed: list[str] = []

    for definition in RESERVATION_SOURCE_DEFINITIONS:
        if not definition.available or definition.collector is None:
            continue
        try:
            rows.extend(definition.collector(user, now=moment))
        except Exception:
            # One domain's outage must not decide whether the reader can see the
            # other domain's bookings.
            logger.exception(
                "my_reservations source failed", extra={"source": definition.key}
            )
            failed.append(definition.key)

    counts = dict.fromkeys(RESERVATION_BUCKETS, 0)
    bucketed: list[tuple[str, ReservationSummary]] = []
    for summary in rows:
        bucket = bucket_for(summary, now=moment)
        counts[bucket] += 1
        bucketed.append((bucket, summary))

    bucketed.sort(key=lambda pair: _sort_key(pair[1], bucket=pair[0]))
    return ReservationFeed(
        summaries=tuple(summary for _, summary in bucketed),
        failed_sources=tuple(sorted(failed)),
        counts=counts,
    )
