"""The scoped people directory — the Users destination under Operations.

One view, one contract: read the query string, hand it to
:mod:`apps.user.services.user_directory`, and return what came back. Every
decision that could leak — which users exist, which columns are readable,
which filter values are real — is made in the service, so this module has
nothing to get wrong on its own.
"""

from __future__ import annotations

from typing import cast

from django.http import HttpRequest
from django.views.decorators.http import require_GET
from inertia import inertia

from apps.web.authorization import enforce_policy
from apps.web.contracts import list_response
from apps.web.operations import operations_scope_payload

from ..models import User
from ..services.agent_administration import VIEW_PERMISSION
from ..services.role_assignments import has_effective_permission
from ..services.user_directory import (
    FieldGroup,
    build_directory_page,
    filter_options,
    parse_filters,
    parse_page,
    parse_sort,
)

__all__ = ["user_directory"]


@enforce_policy("operations_admin_users")
@require_GET
@inertia("UserDirectory")
def user_directory(request: HttpRequest):
    actor = cast(User, request.user)
    filters = parse_filters(request.GET)
    sort, direction = parse_sort(request.GET)
    page, summary, groups = build_directory_page(
        actor,
        filters=filters,
        sort=sort,
        direction=direction,
        page=parse_page(request.GET),
    )
    return {
        "users": list_response(
            page.rows,
            page=page.page,
            page_size=page.page_size,
            total_items=page.total,
            filters=filters.as_payload(),
            sort_key=page.sort,
            sort_direction=page.direction,
        ),
        "summary": summary,
        "filterOptions": filter_options(actor, groups=groups),
        "scope": operations_scope_payload(actor),
        # What the page may render at all. The columns themselves are already
        # absent from the rows; this lets the header, the filter bar, and the
        # row actions agree with them instead of rendering empty cells.
        "visible": {
            "administration": FieldGroup.ADMINISTRATION in groups,
            "contract": FieldGroup.CONTRACT in groups,
            "onboarding": FieldGroup.ONBOARDING in groups,
        },
        "canOpenRecord": has_effective_permission(actor, VIEW_PERMISSION),
    }
