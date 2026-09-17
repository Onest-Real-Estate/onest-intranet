"""Training library reads: visibility, filters, ordering, and serialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db.models import Case, IntegerField, Q, QuerySet, Value, When
from django.urls import reverse

from apps.announcements.richtext import body_payload, safe_url
from apps.training.audience import visible_training_content
from apps.training.embeds import embed_payload, parse_embed_url
from apps.training.media_service import (
    attachments_payload,
    primary_media_detail_payload,
)
from apps.training.models import (
    TrainingCategory,
    TrainingContent,
    TrainingEmbed,
    TrainingMedia,
    TrainingModule,
    TrainingProgress,
    TrainingTranscription,
)
from apps.training.presentation import present_category, present_content_type
from apps.training.progress import (
    apply_completion_filter,
    bulk_agent_onboarding_states,
    completion_state,
)
from apps.training.taxonomy import (
    COMPLETION_FILTER_CODES,
    CONTENT_TYPE_CODES,
    CONTENT_TYPE_RECORDING,
    CONTENT_TYPE_TOOL_ONBOARDING,
    CONTENT_TYPE_VIDEO,
    LIBRARY_VIEW_ALL,
    LIBRARY_VIEW_CODES,
    LIBRARY_VIEW_RECOMMENDED,
    LIBRARY_VIEW_REQUIRED,
    is_known_tool_code,
)
from apps.user.models import User
from apps.web.contracts import list_response

PAGE_SIZE = 12
MAX_PAGE_SIZE = 50

_SCOPE_LABELS = {
    "company": "Brokerage-wide",
    "region": "Region",
    "office": "Office",
}

#: Types whose whole point is something to watch. Publishing one without a
#: ready recording or an approved embed ships a play button that opens
#: nothing — and for a tool onboarding guide, an activation step that dead-ends.
_VIDEO_TYPES = frozenset(
    {CONTENT_TYPE_VIDEO, CONTENT_TYPE_RECORDING, CONTENT_TYPE_TOOL_ONBOARDING}
)


def visible_queryset(user: User, *, now=None) -> QuerySet[TrainingContent]:
    return visible_training_content(user, at=now)


@dataclass(frozen=True)
class TrainingFilters:
    category: str = ""
    content_type: str = ""
    required: str = ""
    tool: str = ""
    completion: str = ""
    view: str = LIBRARY_VIEW_ALL
    query: str = ""
    rejected: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_params(cls, params, *, known_category_codes) -> TrainingFilters:
        rejected: list[str] = []

        raw_category = (params.get("category") or "").strip()[:40]
        category = raw_category if raw_category in known_category_codes else ""
        if raw_category and not category:
            rejected.append("category")

        raw_type = (params.get("type") or "").strip()[:32]
        content_type = raw_type if raw_type in CONTENT_TYPE_CODES else ""
        if raw_type and not content_type:
            rejected.append("type")

        raw_required = (params.get("required") or "").strip().lower()
        required = raw_required if raw_required in {"true", "false"} else ""
        if raw_required and not required:
            rejected.append("required")

        raw_tool = (params.get("tool") or "").strip()[:32]
        tool = raw_tool if raw_tool and is_known_tool_code(raw_tool) else ""
        if raw_tool and not tool:
            rejected.append("tool")

        raw_completion = (params.get("completion") or "").strip()[:16]
        completion = raw_completion if raw_completion in COMPLETION_FILTER_CODES else ""
        if raw_completion and not completion:
            rejected.append("completion")

        raw_view = (params.get("view") or LIBRARY_VIEW_ALL).strip()[:16]
        view = raw_view if raw_view in LIBRARY_VIEW_CODES else LIBRARY_VIEW_ALL
        if raw_view and view != raw_view:
            rejected.append("view")

        raw_query = (params.get("q") or "").strip()[:120]

        return cls(
            category=category,
            content_type=content_type,
            required=required,
            tool=tool,
            completion=completion,
            view=view,
            query=raw_query,
            rejected=tuple(rejected),
        )

    def as_payload(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "type": self.content_type,
            "required": self.required,
            "tool": self.tool,
            "completion": self.completion,
            "view": self.view,
            "q": self.query,
            "rejected": list(self.rejected),
        }

    @property
    def active_count(self) -> int:
        return sum(
            1
            for value in (
                self.category,
                self.content_type,
                self.required,
                self.tool,
                self.completion,
            )
            if value
        )


def apply_filters(
    queryset: QuerySet[TrainingContent],
    filters: TrainingFilters,
    *,
    user: User,
) -> QuerySet[TrainingContent]:
    if filters.view == LIBRARY_VIEW_REQUIRED:
        queryset = queryset.filter(is_required=True)
    elif filters.view == LIBRARY_VIEW_RECOMMENDED:
        queryset = queryset.filter(is_required=False)
    if filters.category:
        queryset = queryset.filter(category__code=filters.category)
    if filters.content_type:
        queryset = queryset.filter(content_type=filters.content_type)
    if filters.required == "true":
        queryset = queryset.filter(is_required=True)
    elif filters.required == "false":
        queryset = queryset.filter(is_required=False)
    if filters.tool:
        queryset = queryset.filter(tool_code=filters.tool)
    if filters.completion:
        queryset = apply_completion_filter(
            queryset, user, completion=filters.completion
        )
    if filters.query:
        queryset = queryset.filter(
            Q(title__icontains=filters.query)
            | Q(summary__icontains=filters.query)
            | Q(body__icontains=filters.query)
            | Q(transcription__search_text__icontains=filters.query)
        )
    return queryset


def order_for_library(queryset: QuerySet[TrainingContent]) -> QuerySet[TrainingContent]:
    return queryset.annotate(
        required_rank=Case(
            When(is_required=True, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by("required_rank", "display_order", "title", "pk")


def validation_debt(content: TrainingContent) -> list[tuple[str, Any]]:
    from django.utils.translation import gettext_lazy as _

    from apps.training.audience import selectors_for
    from apps.training.media_service import media_publish_debt
    from apps.training.quiz_service import quiz_is_configured
    from apps.training.session_service import session_is_configured
    from apps.training.taxonomy import CONTENT_TYPE_LIVE_SESSION, CONTENT_TYPE_QUIZ

    debt: list[tuple[str, Any]] = []
    if content.category is None:
        debt.append(("category", _("Choose a category before publishing.")))
    if not content.title.strip():
        debt.append(("title", _("Add a title before publishing.")))
    if content.content_type in _VIDEO_TYPES:
        embed = TrainingEmbed.objects.filter(content=content).first()
        has_embed = embed is not None and bool(embed.url)
        has_media = TrainingMedia.objects.filter(
            content=content,
            is_active=True,
            processing_state=TrainingMedia.ProcessingState.READY,
            role=TrainingMedia.Role.PRIMARY,
        ).exists()
        if not has_embed and not has_media:
            debt.append(
                (
                    "embed",
                    _("Add a video embed or upload a recording before publishing."),
                )
            )
    if content.content_type == CONTENT_TYPE_TOOL_ONBOARDING and not content.tool_code:
        debt.append(("tool_code", _("Choose the tool this onboarding covers.")))
    if content.content_type == CONTENT_TYPE_QUIZ and not quiz_is_configured(content):
        debt.append(
            (
                "quiz",
                _("Add at least one quiz question before publishing."),
            )
        )
    if content.content_type == CONTENT_TYPE_LIVE_SESSION and not session_is_configured(
        content
    ):
        debt.append(
            (
                "session",
                _("Save the live session schedule before publishing."),
            )
        )
    if content.pk is not None and not selectors_for(content).exists():
        debt.append(("audience", _("Choose who this training is for.")))
    debt.extend(media_publish_debt(content))
    return debt


def validation_debt_payload(content: TrainingContent) -> dict[str, Any]:
    debt = validation_debt(content)
    return {
        "isPublishable": not debt,
        "items": [
            {"field": field_name, "message": str(msg)} for field_name, msg in debt
        ],
    }


def _scope_payload(content: TrainingContent) -> dict[str, str]:
    level = content.scope_level
    return {
        "level": level,
        "label": _SCOPE_LABELS[level],
        "officeName": content.owner_office.name,
    }


def _completion_payload(user: User, content: TrainingContent) -> dict[str, Any]:
    row = TrainingProgress.objects.filter(user=user, content=content).first()
    if row is None:
        return {
            "status": "not_started",
            "label": "Not Started",
            "progressPercent": None,
            "completedAt": None,
            "startedAt": None,
        }
    return {
        "status": row.status,
        "label": row.status.replace("_", " ").title(),
        "progressPercent": row.progress_percent,
        "completedAt": row.completed_at.isoformat() if row.completed_at else None,
        "startedAt": row.started_at.isoformat() if row.started_at else None,
    }


def library_row(
    content: TrainingContent,
    *,
    user: User,
    completion: str | None = None,
) -> dict[str, Any]:
    status = completion or completion_state(user, [content.pk])[content.pk]
    return {
        "id": content.pk,
        "slug": content.slug,
        "title": content.title,
        "summary": content.summary,
        "contentType": present_content_type(content.content_type),
        "category": present_category(content.category),
        "scope": _scope_payload(content),
        "isRequired": content.is_required,
        "estimatedMinutes": content.estimated_minutes,
        "toolCode": content.tool_code or None,
        "completion": {
            "status": status,
            "label": status.replace("_", " ").title(),
            "progressPercent": None,
            "completedAt": None,
            "startedAt": None,
        },
        "publishedAt": (
            content.published_at.isoformat() if content.published_at else None
        ),
        "detailUrl": reverse("training_detail", args=[content.pk]),
    }


def _transcription_payload(content: TrainingContent) -> dict[str, Any] | None:
    transcription = TrainingTranscription.objects.filter(content=content).first()
    if transcription is None:
        return None
    segments = transcription.segments or []
    return {
        "segments": [
            {
                "startMs": int(segment.get("startMs", 0)),
                "endMs": int(segment.get("endMs", 0)),
                "text": str(segment.get("text", "")),
            }
            for segment in segments
            if isinstance(segment, dict)
        ],
        "hasSearchableText": bool(transcription.search_text.strip()),
    }


def _embed_detail(content: TrainingContent) -> dict[str, Any] | None:
    embed = TrainingEmbed.objects.filter(content=content).first()
    if embed is None or not embed.url:
        return None
    parsed = parse_embed_url(embed.url)
    if parsed is None:
        return {"url": embed.url, "provider": embed.provider, "available": False}
    return {**embed_payload(parsed), "available": True}


def _modules_payload(content: TrainingContent, *, user: User) -> list[dict]:
    modules = (
        TrainingModule.objects.filter(course=content)
        .select_related("child", "child__category")
        .order_by("sort_order", "pk")
    )
    child_ids = list(modules.values_list("child_id", flat=True))
    visible_ids = set(
        visible_queryset(user).filter(pk__in=child_ids).values_list("pk", flat=True)
    )
    completion_map = completion_state(user, child_ids)
    rows = []
    for module in modules:
        child = module.child
        if child.pk not in visible_ids:
            continue
        status = completion_map.get(child.pk, "not_started")
        rows.append(
            {
                "id": child.pk,
                "title": child.title,
                "contentType": present_content_type(child.content_type),
                "sortOrder": module.sort_order,
                "estimatedMinutes": child.estimated_minutes,
                "completion": {
                    "status": status,
                    "label": status.replace("_", " ").title(),
                },
                "detailUrl": reverse("training_detail", args=[child.pk]),
            }
        )
    return rows


def _interactivity_for(content: TrainingContent) -> str:
    from apps.training.quiz_service import quiz_is_configured
    from apps.training.session_service import session_is_configured
    from apps.training.taxonomy import (
        CONTENT_TYPE_COURSE,
        CONTENT_TYPE_LIVE_SESSION,
        CONTENT_TYPE_QUIZ,
    )

    if content.content_type == CONTENT_TYPE_QUIZ:
        return "available" if quiz_is_configured(content) else "unavailable"
    if content.content_type == CONTENT_TYPE_LIVE_SESSION:
        return "available" if session_is_configured(content) else "unavailable"
    if content.content_type == CONTENT_TYPE_COURSE:
        return "available"
    if content.is_interactive:
        return "unavailable"
    return "available"


def detail_payload(content: TrainingContent, *, user: User) -> dict[str, Any]:
    from apps.training.certificate_service import certificate_payload
    from apps.training.course_service import course_rollup
    from apps.training.quiz_service import quiz_payload
    from apps.training.session_service import session_payload
    from apps.training.taxonomy import CONTENT_TYPE_COURSE

    row = library_row(content, user=user)
    row["completion"] = _completion_payload(user, content)
    interactivity = _interactivity_for(content)
    external = None
    if content.external_url and safe_url(content.external_url):
        external = {"url": content.external_url, "label": "Open resource"}

    modules = _modules_payload(content, user=user)
    rollup = None
    if content.content_type == CONTENT_TYPE_COURSE:
        rollup = course_rollup(user, content)
        if (
            rollup["percent"] is not None
            and row["completion"]["progressPercent"] is None
        ):
            row["completion"]["progressPercent"] = rollup["percent"]

    return {
        **row,
        "body": content.body,
        "bodyBlocks": body_payload(content.body),
        "externalUrl": external,
        "embed": _embed_detail(content),
        "primaryMedia": primary_media_detail_payload(content),
        "attachments": attachments_payload(content),
        "transcription": _transcription_payload(content),
        "modules": modules,
        "courseRollup": rollup,
        "interactivity": interactivity,
        "completion": row["completion"],
        "quiz": quiz_payload(content, user),
        "liveSession": session_payload(content, user),
        "certificate": certificate_payload(content, user),
        "versionNumber": content.version_number,
        "versionCompletionPolicy": content.version_completion_policy,
        "canMarkComplete": (
            not content.is_interactive and row["completion"]["status"] != "completed"
        ),
        "canMarkStarted": row["completion"]["status"] == "not_started",
    }


def build_library(
    user: User,
    *,
    params,
    page: int,
    page_size: int = PAGE_SIZE,
) -> dict[str, Any]:
    from apps.training.required_status import required_training_summary

    known_codes = frozenset(
        TrainingCategory.objects.active().values_list("code", flat=True)
    )
    filters = TrainingFilters.from_params(params, known_category_codes=known_codes)
    queryset = apply_filters(visible_queryset(user), filters, user=user)
    queryset = order_for_library(queryset)
    size = max(1, min(page_size, MAX_PAGE_SIZE))
    total = queryset.count()
    total_pages = max(1, (total + size - 1) // size)
    current = min(max(page, 1), total_pages)
    start = (current - 1) * size
    page_items = list(queryset[start : start + size])
    completion_map = completion_state(user, [item.pk for item in page_items])
    rows = [
        library_row(item, user=user, completion=completion_map[item.pk])
        for item in page_items
    ]
    payload = list_response(
        rows,
        page=current,
        page_size=size,
        total_items=total,
        filters=filters.as_payload(),
    )
    payload["filters"] = filters.as_payload()
    payload["requiredSummary"] = required_training_summary(user)
    return payload


def category_filter_options(*, include_codes=()) -> list[dict[str, str]]:
    codes = set(include_codes)
    rows = TrainingCategory.objects.filter(
        Q(is_active=True) | Q(code__in=codes)
    ).order_by("display_order", "label")
    return [{"value": row.code, "label": row.label} for row in rows]


def content_type_filter_options() -> list[dict[str, str]]:
    return [
        {"value": code, "label": present_content_type(code)["label"]}
        for code in sorted(CONTENT_TYPE_CODES)
    ]


def tool_filter_options() -> list[dict[str, str]]:
    """Tools content can be tagged with: the live catalog, in catalog order.

    Two bounded queries, never one per option. Legacy codes still carried by
    published content keep an option so an existing filter does not silently
    stop matching anything.
    """
    from apps.onboarding_tools.models import OnboardingTool
    from apps.training.models import TrainingContent

    options = {
        tool.slug: tool.name
        for tool in OnboardingTool.objects.live().order_by(
            "group", "sort_order", "name"
        )
    }
    still_tagged = set(
        TrainingContent.objects.exclude(tool_code="")
        .values_list("tool_code", flat=True)
        .distinct()
    )
    for code in sorted(still_tagged - set(options)):
        options[code] = code.replace("-", " ").replace("_", " ").title()
    return [{"value": value, "label": label} for value, label in options.items()]


def completion_filter_options() -> list[dict[str, str]]:
    from apps.training.taxonomy import COMPLETION_CHOICES

    return [{"value": code, "label": str(label)} for code, label in COMPLETION_CHOICES]


__all__ = [
    "TrainingFilters",
    "apply_filters",
    "build_library",
    "bulk_agent_onboarding_states",
    "category_filter_options",
    "completion_filter_options",
    "content_type_filter_options",
    "detail_payload",
    "library_row",
    "order_for_library",
    "tool_filter_options",
    "validation_debt",
    "validation_debt_payload",
    "visible_queryset",
]
