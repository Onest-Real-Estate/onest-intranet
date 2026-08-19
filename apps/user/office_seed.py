"""Seed the Onest org tree (head office → region → regional office → branch).

The listed markets are the locations Onest currently serves; they sit under
Mid-Atlantic and New England. Users pick an *assignable* office (head office,
a regional office that is itself a served market, or a branch).

Re-running is safe in any environment. Each call returns a SeedReport with
counts so callers (migrations, management commands) can log outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SeedReport:
    created: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)
    # Slug exists but name or kind differs — seed stops and raises.
    conflicting: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        parts = [
            f"created={len(self.created)}",
            f"matched={len(self.matched)}",
            f"conflicting={len(self.conflicting)}",
        ]
        return "SeedReport(" + ", ".join(parts) + ")"


class SeedConflictError(Exception):
    """Raised when a slug is owned by a record with incompatible name/kind."""


def upsert_office(
    office_model,
    report: SeedReport,
    *,
    slug: str,
    name: str,
    kind: str,
    parent=None,
    is_assignable: bool = True,
    sort_order: int = 0,
):
    """
    Look up by slug (the stable key). Three outcomes:

    - **Created**: no record with this slug → insert with all fields including
      ``is_active=True``.
    - **Matched**: slug found AND name+kind agree → update only the structural
      fields (parent, is_assignable, sort_order) that may legitimately drift.
      ``is_active`` is intentionally NOT touched so an admin deactivation is
      preserved.
    - **Conflict**: slug found BUT name or kind differs → raises
      ``SeedConflictError`` with an actionable message; caller should abort the
      transaction.
    """
    try:
        existing = office_model.objects.select_for_update().get(slug=slug)
    except office_model.DoesNotExist:
        existing = None

    if existing is None:
        create_kwargs = {
            "slug": slug,
            "name": name,
            "kind": kind,
            "parent": parent,
            "is_assignable": is_assignable,
            "is_active": True,
            "sort_order": sort_order,
        }
        field_names = {field.name for field in office_model._meta.get_fields()}
        if "stable_key" in field_names:
            create_kwargs["stable_key"] = slug
        office = office_model.objects.create(**create_kwargs)
        report.created.append(slug)
        return office

    # Slug exists — check for conflicts before touching anything.
    if existing.name != name or existing.kind != kind:
        report.conflicting.append(slug)
        raise SeedConflictError(
            f"Slug '{slug}' already belongs to office '{existing.name}' "
            f"(kind={existing.kind}), but the seed expects name='{name}' "
            f"kind='{kind}'. Resolve this manually before re-seeding."
        )

    # Matched: update structural fields only; preserve is_active.
    updates = {
        "parent": parent,
        "is_assignable": is_assignable,
        "sort_order": sort_order,
    }
    if hasattr(existing, "stable_key") and not existing.stable_key:
        updates["stable_key"] = slug
    office_model.objects.filter(pk=existing.pk).update(**updates)
    existing.refresh_from_db()
    report.matched.append(slug)
    return existing


def seed_offices(office_model=None) -> SeedReport:
    """Idempotent: safe to re-run. Returns a SeedReport."""
    from apps.user.models import Office as LiveOffice

    Office = office_model or LiveOffice
    report = SeedReport()

    # String literals so this also runs against historical migration models
    # (they don't carry the Office.Kind enum).
    head_office = "head_office"
    region = "region"
    regional_office = "regional_office"
    branch = "branch"

    head = upsert_office(
        Office,
        report,
        slug="onest-head-office",
        name="Onest Real Estate",
        kind=head_office,
        is_assignable=True,
        sort_order=0,
    )

    mid_atlantic = upsert_office(
        Office,
        report,
        slug="region-mid-atlantic",
        name="Mid-Atlantic",
        kind=region,
        parent=head,
        is_assignable=False,
        sort_order=10,
    )
    new_england = upsert_office(
        Office,
        report,
        slug="region-new-england",
        name="New England",
        kind=region,
        parent=head,
        is_assignable=False,
        sort_order=20,
    )

    virginia = upsert_office(
        Office,
        report,
        slug="ro-virginia",
        name="Virginia",
        kind=regional_office,
        parent=mid_atlantic,
        is_assignable=False,
        sort_order=10,
    )
    upsert_office(
        Office,
        report,
        slug="charlottesville-va",
        name="Charlottesville VA",
        kind=branch,
        parent=virginia,
        sort_order=10,
    )
    upsert_office(
        Office,
        report,
        slug="fairfax-va",
        name="Fairfax VA",
        kind=branch,
        parent=virginia,
        sort_order=20,
    )

    upsert_office(
        Office,
        report,
        slug="district-of-columbia",
        name="District of Columbia",
        kind=regional_office,
        parent=mid_atlantic,
        sort_order=20,
    )
    upsert_office(
        Office,
        report,
        slug="maryland",
        name="Maryland",
        kind=regional_office,
        parent=mid_atlantic,
        sort_order=30,
    )

    pennsylvania = upsert_office(
        Office,
        report,
        slug="ro-pennsylvania",
        name="Pennsylvania",
        kind=regional_office,
        parent=mid_atlantic,
        is_assignable=False,
        sort_order=40,
    )
    upsert_office(
        Office,
        report,
        slug="harrisburg",
        name="Harrisburg",
        kind=branch,
        parent=pennsylvania,
        sort_order=10,
    )
    upsert_office(
        Office,
        report,
        slug="philadelphia",
        name="Philadelphia",
        kind=branch,
        parent=pennsylvania,
        sort_order=20,
    )
    upsert_office(
        Office,
        report,
        slug="pittsburgh",
        name="Pittsburgh",
        kind=branch,
        parent=pennsylvania,
        sort_order=30,
    )

    for order, (slug, name) in enumerate(
        (
            ("connecticut", "Connecticut"),
            ("massachusetts", "Massachusetts"),
            ("new-hampshire", "New Hampshire"),
            ("rhode-island", "Rhode Island"),
        ),
        start=10,
    ):
        upsert_office(
            Office,
            report,
            slug=slug,
            name=name,
            kind=regional_office,
            parent=new_england,
            sort_order=order,
        )

    return report
