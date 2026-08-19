"""Dummy oNEST HUB dashboard payloads.

These are stand-ins until transactions, calendar, news, and documents have
real models. Loaders are used with ``inertia.defer`` so the hub chrome paints
before this data arrives.
"""

from __future__ import annotations

import os
import time
from typing import Any

from django.conf import settings

HUB_SECTIONS: dict[str, str] = {
    "my-contract": "My contract",
    "agent-transactions": "Agent transactions",
    "my-reservations": "My reservations",
    "office-info": "Office info",
    "office-resources": "Office resources",
    "office-inventory": "Office inventory",
    "training-learning": "Training & learning",
    "documents-forms": "Documents & forms",
    "marketing-resources": "Marketing resources",
    "policies-compliance": "Policies & compliance",
    "agent-directory": "Agent directory",
}


def _maybe_delay() -> None:
    """Slow dummy loaders in local DEBUG so skeletons are visible.

    Pytest sets ``PYTEST_CURRENT_TEST``; never sleep in tests.
    """
    if settings.DEBUG and not os.environ.get("PYTEST_CURRENT_TEST"):
        time.sleep(0.35)


def dashboard_stats() -> dict[str, Any]:
    _maybe_delay()
    return {
        "activeTransactions": {
            "value": "6",
            "hint": "2 require attention",
            "tone": "alert",
        },
        "upcomingClosings": {
            "value": "3",
            "hint": "Next 30 days",
            "tone": "default",
        },
        "pendingTasks": {
            "value": "4",
            "hint": "2 due this week",
            "tone": "warning",
        },
        "commissionYtd": {
            "value": "$48,750",
            "hint": "+12.4% vs last year",
            "tone": "success",
        },
    }


def dashboard_quick_apps() -> list[dict[str, str]]:
    _maybe_delay()
    return [
        {"id": "lofty", "name": "Lofty", "href": "https://www.lofty.com"},
        {"id": "skyslope", "name": "SkySlope", "href": "https://www.skyslope.com"},
        {
            "id": "microsoft365",
            "name": "Microsoft 365",
            "href": "https://www.microsoft365.com",
        },
        {"id": "dotloop", "name": "Dotloop", "href": "https://www.dotloop.com"},
    ]


def dashboard_announcements() -> dict[str, Any]:
    _maybe_delay()
    return {
        "featured": {
            "tag": "Company news",
            "title": "New agent resources and transaction updates",
            "excerpt": (
                "Updated checklists, commission forms, and office hours "
                "are live in the hub."
            ),
            "imageUrl": "https://picsum.photos/seed/onest-news/640/400",
        },
        "items": [
            {
                "tag": "Market update",
                "title": "Mid-Atlantic inventory ticked up this week",
                "excerpt": (
                    "Fairfax and Charlottesville saw the largest week-over-week gains."
                ),
            },
            {
                "tag": "Event",
                "title": "New-agent training, Thursday 10:00 AM",
                "excerpt": "Conference Room B — bring your laptop and MLS login.",
            },
        ],
    }


def dashboard_transactions() -> list[dict[str, str]]:
    _maybe_delay()
    return [
        {
            "id": "tx-1",
            "address": "1842 Maple Ave, Fairfax VA",
            "imageUrl": "https://picsum.photos/seed/onest-tx1/80/80",
            "type": "Buy",
            "stage": "Under contract",
            "closing": "Sep 4",
            "status": "on_track",
        },
        {
            "id": "tx-2",
            "address": "910 King St, Alexandria VA",
            "imageUrl": "https://picsum.photos/seed/onest-tx2/80/80",
            "type": "Sell",
            "stage": "Inspection",
            "closing": "Aug 28",
            "status": "action_needed",
        },
        {
            "id": "tx-3",
            "address": "44 U St NW, Washington DC",
            "imageUrl": "https://picsum.photos/seed/onest-tx3/80/80",
            "type": "Buy",
            "stage": "Clear to close",
            "closing": "Sep 12",
            "status": "on_track",
        },
        {
            "id": "tx-4",
            "address": "2207 Grove Ave, Richmond VA",
            "imageUrl": "https://picsum.photos/seed/onest-tx4/80/80",
            "type": "Sell",
            "stage": "Attorney review",
            "closing": "Sep 18",
            "status": "action_needed",
        },
    ]


def dashboard_training() -> dict[str, Any]:
    _maybe_delay()
    return {
        "percent": 72,
        "label": "New agent training",
        "resourceTitle": "Marketing toolkit",
        "resourceHint": "Flyers, social templates, and brand assets.",
    }


def dashboard_schedule() -> dict[str, Any]:
    _maybe_delay()
    return {
        "dateLabel": "Aug 19",
        "events": [
            {
                "time": "10:00 AM",
                "title": "Team training",
                "place": "Conference Room B",
            },
            {
                "time": "1:30 PM",
                "title": "Client consultation",
                "place": "Virtual",
            },
        ],
    }


def dashboard_action_items() -> dict[str, Any]:
    _maybe_delay()
    return {
        "total": 3,
        "items": [
            {
                "id": "task-1",
                "title": "Upload inspection documents",
                "property": "910 King St, Alexandria VA",
                "due": "Yesterday",
                "late": True,
            },
            {
                "id": "task-2",
                "title": "Confirm appraisal appointment",
                "property": "1842 Maple Ave, Fairfax VA",
                "due": "Today",
                "late": False,
            },
            {
                "id": "task-3",
                "title": "Send buyer disclosures",
                "property": "44 U St NW, Washington DC",
                "due": "Aug 21",
                "late": False,
            },
        ],
    }


def dashboard_market() -> dict[str, Any]:
    _maybe_delay()
    return {
        "rates": [
            {"label": "30-year fixed", "value": "6.73%", "bar": 73},
            {"label": "15-year fixed", "value": "6.30%", "bar": 63},
        ]
    }


def dashboard_documents() -> list[dict[str, str]]:
    _maybe_delay()
    return [
        {"id": "doc-1", "name": "Commission split agreement"},
        {"id": "doc-2", "name": "Agent handbook 2024"},
        {"id": "doc-3", "name": "Independent contractor agreement"},
    ]
