"""Scope helpers for reports — always apply before aggregation."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.user.models import User
from apps.user.services.role_assignments import EffectiveAccess, get_effective_access
from apps.web.authorization import scope_queryset_for_user_office
from apps.web.metrics import MetricScope, resolve_scope


def report_scope(
    user: User, *, access: EffectiveAccess | None = None
) -> tuple[EffectiveAccess, str]:
    effective = get_effective_access(user) if access is None else access
    return effective, resolve_scope(user, effective)


def scoped_users(
    user: User,
    *,
    access: EffectiveAccess,
    office_stable_key: str | None = None,
) -> QuerySet[User]:
    """People in the actor's effective office tree, optionally narrowed further.

    A client-supplied office key outside scope yields an empty queryset — never
    a wider one, and never a signal that the office exists.
    """
    queryset = scope_queryset_for_user_office(
        user,
        User.objects.select_related("office", "office__region"),
        field_name="office",
        access=access,
    )
    if office_stable_key:
        queryset = queryset.filter(office__stable_key=office_stable_key)
        if not access.company_wide:
            allowed_offices = set(access.office_keys)
            if access.region_keys:
                from apps.user.models import Office

                allowed_offices |= set(
                    Office.objects.filter(
                        region__stable_key__in=sorted(access.region_keys)
                    ).values_list("stable_key", flat=True)
                )
            if office_stable_key not in allowed_offices:
                return queryset.none()
    return queryset


def scope_label(access: EffectiveAccess, scope: str) -> str:
    if scope == MetricScope.COMPANY or access.company_wide:
        return "Brokerage-wide"
    if scope == MetricScope.REGION and access.region_keys:
        return f"{len(access.region_keys)} region(s)"
    if scope == MetricScope.OFFICE and access.office_keys:
        return f"{len(access.office_keys)} office(s)"
    if scope == MetricScope.SELF:
        return "Self"
    return "No administrative scope"
