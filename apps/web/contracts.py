"""Stable payload conventions shared by Django views and Inertia pages."""

from collections.abc import Iterable, Mapping
from typing import Any

from django import forms


def validation_errors(form: forms.BaseForm) -> dict[str, Any]:
    """Preserve every server message and separate form-level failures."""
    data = form.errors.get_json_data()
    form_messages = [error["message"] for error in data.pop("__all__", [])]
    return {
        "fields": {
            field: [error["message"] for error in errors]
            for field, errors in data.items()
        },
        "form": form_messages,
    }


def empty_validation_errors() -> dict[str, Any]:
    return {"fields": {}, "form": []}


def list_response(
    items: Iterable[Any],
    *,
    page: int,
    page_size: int,
    total_items: int,
    filters: Mapping[str, Any] | None = None,
    sort_key: str | None = None,
    sort_direction: str = "asc",
) -> dict[str, Any]:
    """Return the canonical paginated/list payload consumed by shared tables."""
    page_size = max(1, page_size)
    total_items = max(0, total_items)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    current_page = min(max(page, 1), total_pages)
    sort = None
    if sort_key:
        sort = {
            "key": sort_key,
            "direction": "desc" if sort_direction == "desc" else "asc",
        }
    return {
        "items": list(items),
        "pagination": {
            "page": current_page,
            "pageSize": page_size,
            "totalItems": total_items,
            "totalPages": total_pages,
            "hasNext": current_page < total_pages,
            "hasPrevious": current_page > 1,
        },
        "filters": dict(filters or {}),
        "sort": sort,
    }
