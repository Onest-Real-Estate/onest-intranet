"""The scoped people directory — the Users destination under Operations.

One view, one contract: read the query string, hand it to
:mod:`apps.user.services.user_directory`, and return what came back. Every
decision that could leak — which users exist, which columns are readable,
which filter values are real — is made in the service, so this module has
nothing to get wrong on its own.
"""

from __future__ import annotations

from typing import Any, cast

from django.http import HttpRequest
from django.shortcuts import redirect
from django.views.decorators.http import require_GET
from inertia import inertia

from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors, list_response
from apps.web.operations import operations_scope_payload

from ..models import User
from ..services.agent_administration import VIEW_PERMISSION
from ..services.role_assignments import has_effective_permission
from ..services.user_directory import (
    PAGE_SIZE_OPTIONS,
    FieldGroup,
    build_directory_page,
    filter_options,
    parse_filters,
    parse_page,
    parse_page_size,
    parse_sort,
)

__all__ = ["people_hub", "user_directory"]

#: The People tabs in the order they appear, each with the grant that opens
#: it. The first one the reader holds is where the navigation lands.
PEOPLE_TABS: tuple[tuple[str, str], ...] = (
    ("admin_users", "web.view_users"),
    ("admin_assign_roles", "web.assign_user_roles"),
    ("admin_new_agents", "web.view_new_agents"),
)


def directory_props(
    actor: User, params, *, errors: dict | None = None
) -> dict[str, Any]:
    """The Users list for ``params``. Shared with the account-state write, which
    re-renders this list — not the person's record — when a lockout started
    from a row is refused."""
    filters = parse_filters(params)
    sort, direction = parse_sort(params)
    page, summary, groups = build_directory_page(
        actor,
        filters=filters,
        sort=sort,
        direction=direction,
        page=parse_page(params),
        page_size=parse_page_size(params),
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
        "pageSizeOptions": list(PAGE_SIZE_OPTIONS),
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
        "errors": errors or empty_validation_errors(),
    }


@enforce_policy("operations_admin_users")
@require_GET
@inertia("UserDirectory")
def user_directory(request: HttpRequest):
    return directory_props(cast(User, request.user), request.GET)


@enforce_policy("operations_people")
@require_GET
def people_hub(request: HttpRequest):
    """Land on the first People tab this reader may open."""
    actor = cast(User, request.user)
    for route_name, permission in PEOPLE_TABS:
        if has_effective_permission(actor, permission):
            return redirect(route_name)
    # The policy already required one of the grants; reaching here means the
    # grants and the tab list have drifted apart.
    return redirect("dashboard")
