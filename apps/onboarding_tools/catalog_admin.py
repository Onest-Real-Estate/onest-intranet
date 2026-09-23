"""What the catalog management screen reads.

The editor used to see a tool as its own fields and nothing else. An
administrator deciding whether a row is *finished* needs three more facts, and
each is read here in a bounded number of queries whatever the catalog size:

* **Health** — the gaps that make a row worse for agents: no training anybody
  can watch, nothing to open, an audience that reaches nobody.
* **Training** — which items are tagged with the tool, by lifecycle, and which
  of them this administrator may open in the training workspace.
* **Adoption** — how many agents *within this reader's reach* are ready,
  blocked, or have ticked the tool themselves and are waiting on a check.
  Scoped in SQL like every other count: a total is a disclosure too.

Nothing here writes. Saves and reorders stay in :mod:`services`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from django.db.models import Count, Q
from django.urls import reverse

from apps.onboarding_tools.models import (
    COMPLETE_STATES,
    AgentToolStatus,
    OnboardingTool,
    Provisioning,
    ToolGroup,
    ToolState,
)
from apps.user.models import Office


class ToolHealth(StrEnum):
    """A gap on one catalog row, worst first."""

    NO_AUDIENCE = "no_audience"
    NO_TRAINING = "no_training"
    NO_OPEN_LINK = "no_open_link"


#: Gaps that put a row on the "needs attention" list. A missing open link is
#: named on the row but does not count: flagging nearly every tool for it
#: would bury the two gaps that actually leave an agent stuck.
ATTENTION: frozenset[ToolHealth] = frozenset(
    {ToolHealth.NO_AUDIENCE, ToolHealth.NO_TRAINING}
)

HEALTH_LABELS: dict[ToolHealth, str] = {
    ToolHealth.NO_AUDIENCE: "Reaches no office",
    ToolHealth.NO_TRAINING: "No published training",
    ToolHealth.NO_OPEN_LINK: "No link to open it",
}


class CatalogShow(StrEnum):
    """Which rows the list is narrowed to. Kept in the URL."""

    ALL = "all"
    ATTENTION = "attention"
    ACTIVE = "active"
    INACTIVE = "inactive"


#: How many training items a row names before it says "and N more".
TRAINING_PREVIEW = 3


@dataclass(frozen=True)
class CatalogFilters:
    q: str = ""
    show: CatalogShow = CatalogShow.ALL

    @classmethod
    def from_params(cls, params) -> CatalogFilters:
        raw = (params.get("show") or "").strip()
        show = CatalogShow(raw) if raw in CatalogShow._value2member_map_ else None
        return cls(
            q=(params.get("q") or "").strip()[:80],
            show=show or CatalogShow.ALL,
        )

    @property
    def narrowed(self) -> bool:
        return bool(self.q) or self.show != CatalogShow.ALL

    def payload(self) -> dict[str, str]:
        return {"q": self.q, "show": self.show.value}


def office_paths(offices: list[Office]) -> dict[int, str]:
    """``Region / State / Branch`` for every office, from one read.

    ``Office.path_label`` walks ``parent`` one query per level; across two
    hundred offices that is the N+1 this avoids. Parents outside the reader's
    scope still name the path, because the whole tree is read once.
    """
    nodes = {
        row["pk"]: row
        for row in Office.objects.values("pk", "name", "parent_id").order_by()
    }
    paths: dict[int, str] = {}
    for office in offices:
        names: list[str] = []
        seen: set[int] = set()
        node = nodes.get(office.pk)
        while node is not None and node["pk"] not in seen:
            seen.add(node["pk"])
            names.append(node["name"])
            node = nodes.get(node["parent_id"])
        paths[office.pk] = " / ".join(reversed(names))
    return paths


def _training_by_tool(actor, slugs: list[str]) -> dict[str, dict[str, Any]]:
    """Tagged training per tool: lifecycle counts, and the items this reader
    may open in the training workspace.

    Counts cover every item so "no published training" is true brokerage-wide;
    the openable list is the reader's own manageable set, so an edit link never
    leads to a 404.
    """
    from apps.training.administration import manageable_queryset
    from apps.training.models import TrainingContent

    result: dict[str, dict[str, Any]] = {
        slug: {"published": 0, "draft": 0, "items": [], "more": 0} for slug in slugs
    }
    if not slugs:
        return result

    counts = (
        TrainingContent.objects.filter(tool_code__in=slugs)
        .exclude(status=TrainingContent.Status.ARCHIVED)
        .values("tool_code", "status")
        .annotate(total=Count("pk"))
        .order_by()
    )
    for row in counts:
        key = (
            "published"
            if row["status"] == TrainingContent.Status.PUBLISHED
            else "draft"
        )
        result[row["tool_code"]][key] += row["total"]

    openable = (
        manageable_queryset(actor)
        .filter(tool_code__in=slugs)
        .exclude(status=TrainingContent.Status.ARCHIVED)
        .select_related(None)
        .only("pk", "title", "status", "tool_code", "display_order")
        .order_by("tool_code", "display_order", "-version_number", "-pk")
    )
    for content in openable:
        entry = result[content.tool_code]
        if len(entry["items"]) >= TRAINING_PREVIEW:
            entry["more"] += 1
            continue
        entry["items"].append(
            {
                "id": content.pk,
                "title": content.title,
                "published": content.status == TrainingContent.Status.PUBLISHED,
                "href": reverse("training_edit", args=[content.pk]),
            }
        )
    return result


def _adoption_by_tool(actor) -> dict[int, dict[str, int]]:
    """Ready, blocked, and ticked-but-unconfirmed counts per tool, within the
    reader's own reach. One aggregate query."""
    from apps.web.capability import access_for

    rows = (
        AgentToolStatus.objects.for_reader(actor, access=access_for(actor))
        .filter(agent__is_active=True)
        .exclude(agent=actor)
        .values("tool_id")
        .annotate(
            ready=Count("pk", filter=Q(state=ToolState.READY), distinct=True),
            blocked=Count("pk", filter=Q(state=ToolState.BLOCKED), distinct=True),
            awaiting=Count(
                "pk",
                filter=Q(agent_confirmed_at__isnull=False)
                & ~Q(state__in=COMPLETE_STATES),
                distinct=True,
            ),
        )
        .order_by()
    )
    return {
        row["tool_id"]: {
            "ready": row["ready"],
            "blocked": row["blocked"],
            "awaiting": row["awaiting"],
        }
        for row in rows
    }


def _health(tool: OnboardingTool, audiences: list, training: dict) -> list[ToolHealth]:
    if not tool.is_active:
        # A retired row is not a gap anybody needs to close.
        return []
    issues: list[ToolHealth] = []
    if not tool.company_wide and not any(row.office.is_active for row in audiences):
        issues.append(ToolHealth.NO_AUDIENCE)
    if training["published"] == 0:
        issues.append(ToolHealth.NO_TRAINING)
    if not tool.open_url:
        issues.append(ToolHealth.NO_OPEN_LINK)
    return issues


def needs_attention(health: list[ToolHealth]) -> bool:
    return any(issue in ATTENTION for issue in health)


def _matches(filters: CatalogFilters, tool: OnboardingTool, health: list) -> bool:
    if filters.q:
        needle = filters.q.lower()
        haystack = f"{tool.name} {tool.slug} {tool.description}".lower()
        if needle not in haystack:
            return False
    if filters.show == CatalogShow.ACTIVE:
        return tool.is_active
    if filters.show == CatalogShow.INACTIVE:
        return not tool.is_active
    if filters.show == CatalogShow.ATTENTION:
        return needs_attention(health)
    return True


def catalog_rows(actor, filters: CatalogFilters) -> dict[str, Any]:
    """Every shelf with its rows, plus the figures the summary strip reads."""
    tools = list(
        OnboardingTool.objects.all()
        .prefetch_related("office_audiences__office")
        .order_by("group", "sort_order", "name")
    )
    slugs = [tool.slug for tool in tools]
    training = _training_by_tool(actor, slugs)
    adoption = _adoption_by_tool(actor)
    audience_offices = [
        row.office for tool in tools for row in tool.office_audiences.all()
    ]
    paths = office_paths(audience_offices)
    provisioning_labels = dict(Provisioning.choices)

    summary = {
        "active": 0,
        "inactive": 0,
        "attention": 0,
        "trained": 0,
        "awaiting": 0,
    }
    groups: list[dict[str, Any]] = []
    for code, label in ToolGroup.choices:
        rows = []
        for tool in (tool for tool in tools if tool.group == code):
            audiences = list(tool.office_audiences.all())
            coverage = training[tool.slug]
            health = _health(tool, audiences, coverage)
            counts = adoption.get(tool.pk, {"ready": 0, "blocked": 0, "awaiting": 0})

            if tool.is_active:
                summary["active"] += 1
                summary["attention"] += 1 if needs_attention(health) else 0
                summary["trained"] += 1 if coverage["published"] else 0
                summary["awaiting"] += counts["awaiting"]
            else:
                summary["inactive"] += 1

            if not _matches(filters, tool, health):
                continue
            rows.append(
                {
                    "slug": tool.slug,
                    "name": tool.name,
                    "description": tool.description,
                    "group": tool.group,
                    "provisioning": tool.provisioning,
                    "provisioningLabel": str(
                        provisioning_labels.get(tool.provisioning, "")
                    ),
                    "openUrl": tool.open_url,
                    "helpUrl": tool.help_url,
                    "steps": [str(step) for step in (tool.setup_steps or [])],
                    "contact": tool.contact_label,
                    "requestPath": tool.request_path,
                    "companyWide": tool.company_wide,
                    # Named in words, because "not company-wide" tells an
                    # administrator nothing about who actually gets it.
                    "appliesTo": (
                        "Everywhere"
                        if tool.company_wide
                        else ", ".join(row.office.name for row in audiences)
                        or "Nobody yet"
                    ),
                    "audience": [
                        {
                            "id": row.office_id,
                            "name": row.office.name,
                            "path": paths.get(row.office_id, row.office.name),
                            "active": row.office.is_active,
                        }
                        for row in audiences
                    ],
                    "officeIds": [row.office_id for row in audiences],
                    "required": tool.is_required,
                    "active": tool.is_active,
                    "sortOrder": tool.sort_order,
                    "health": [
                        {"code": issue.value, "label": HEALTH_LABELS[issue]}
                        for issue in health
                    ],
                    "training": coverage,
                    "adoption": counts,
                }
            )
        groups.append({"code": code, "label": str(label), "tools": rows})
    return {"groups": groups, "summary": summary}
