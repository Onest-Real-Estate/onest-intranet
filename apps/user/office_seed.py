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


# Structured hours schema: one entry per open day; closed days are omitted
# and rendered as "Closed". All oNEST offices operate on Eastern Time.
def weekday_hours() -> list[dict[str, str]]:
    return [
        {"day": day, "open": "09:00", "close": "17:00"}
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday")
    ]


OFFICE_DETAILS: dict[str, dict] = {
    # The seven served markets from the ONEST Regional Offices directory.
    # Parking / building-access copy is intentionally NOT seeded — it must
    # come from verified local operations input, never invented here.
    "massachusetts": {
        "street_address": "301 Edgewater Pl",
        "city": "Wakefield",
        "state": "MA",
        "zip_code": "01880",
        "main_phone": "(857) 869-2765",
        "public_email": "suman@onest.realestate",
    },
    "harrisburg": {
        "street_address": "2600 Commerce Dr Ste 1",
        "city": "Harrisburg",
        "state": "PA",
        "zip_code": "17110-9368",
        "main_phone": "(730) 608-9412",
        "public_email": "bishwa@onest.realestate",
    },
    "pittsburgh": {
        "street_address": "4101 Brownsville Rd Suite 200",
        "city": "Pittsburgh",
        "state": "PA",
        "zip_code": "15227",
        "main_phone": "(412) 515-1429",
        "public_email": "srai@onest.realestate",
    },
    "philadelphia": {
        # Directory screenshot showed malladhakal@ones.realestate (missing
        # the "t"); treated as a typo and normalized to the onest domain.
        "street_address": "25 Sentry Parkway Building 5",
        "city": "Blue Bell",
        "state": "PA",
        "zip_code": "19422",
        "main_phone": "(551) 254-0620",
        "public_email": "malladhakal@onest.realestate",
    },
    "connecticut": {
        "street_address": "119 Montowese St.",
        "city": "Branford",
        "state": "CT",
        "zip_code": "06405",
        "main_phone": "(617) 229-9883",
        "public_email": "chiran@onest.realestate",
    },
    "new-hampshire": {
        "street_address": "350 Harvey Road",
        "city": "Manchester",
        "state": "NH",
        "zip_code": "03103",
        "main_phone": "(617) 319-9541",
        "public_email": "ranjan@onest.realestate",
    },
    "charlottesville-va": {
        "street_address": "1024 Carrington Pl",
        "city": "Charlottesville",
        "state": "VA",
        "zip_code": "22901",
        "main_phone": "(571) 222-5555",
        "public_email": "prashanna@onest.realestate",
    },
    "fairfax-va": {
        "street_address": "",
        "city": "Fairfax",
        "state": "VA",
        "zip_code": "",
        "main_phone": "",
        "public_email": "",
    },
    "maryland": {
        "street_address": "",
        "city": "",
        "state": "MD",
        "zip_code": "",
        "main_phone": "",
        "public_email": "",
    },
    "ro-virginia": {
        "street_address": "",
        "city": "",
        "state": "VA",
        "zip_code": "",
        "main_phone": "",
        "public_email": "",
    },
}


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
    details: dict | None = None,
):
    """
    Look up by slug (the stable key). Three outcomes:

    - **Created**: no record with this slug → insert with all fields including
      ``is_active=True``.
    - **Matched**: slug found AND name+kind agree → update only the structural
      fields (parent, is_assignable, sort_order) that may legitimately drift,
      plus any seeded ``details`` (address, phone, email, hours). ``is_active``
      is intentionally NOT touched so an admin deactivation is preserved.
    - **Conflict**: slug found BUT name or kind differs → raises
      SeedConflictError with an actionable message; caller should abort the
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
            **(details or {}),
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

    # Matched: update structural + seeded detail fields; preserve is_active.
    updates = {
        "parent": parent,
        "is_assignable": is_assignable,
        "sort_order": sort_order,
        **(details or {}),
    }
    if hasattr(existing, "stable_key") and not existing.stable_key:
        updates["stable_key"] = slug
    office_model.objects.filter(pk=existing.pk).update(**updates)
    existing.refresh_from_db()
    report.matched.append(slug)
    return existing


def seed_offices(office_model=None) -> SeedReport:
    """Idempotent: safe to re-run. Returns a SeedReport.

    Always runs inside a transaction so ``select_for_update`` locks in
    ``upsert_office`` work under PostgreSQL (including
    ``django_db(transaction=True)`` tests that do not wrap the fixture).
    """
    from django.db import transaction

    from apps.user.models import Office as LiveOffice

    Office = office_model or LiveOffice
    report = SeedReport()

    # String literals so this also runs against historical migration models
    # (they don't carry the Office.Kind enum).
    head_office = "head_office"
    region = "region"
    regional_office = "regional_office"
    branch = "branch"

    with transaction.atomic():
        return _seed_offices_locked(
            Office,
            report,
            head_office=head_office,
            region=region,
            regional_office=regional_office,
            branch=branch,
        )


def _seed_offices_locked(
    Office,
    report: SeedReport,
    *,
    head_office: str,
    region: str,
    regional_office: str,
    branch: str,
) -> SeedReport:
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

    # Second pass: apply the regional-office directory details (address,
    # phone, email, structured hours) on top of whatever was just created or
    # matched. Kept separate so structural seeding above stays untouched.
    # Fields unknown to historical migration models (this also runs from
    # migration 0004) are skipped so old schemas keep seeding safely.
    field_names = {f.name for f in Office._meta.get_fields()}
    for slug, details in OFFICE_DETAILS.items():
        updates = {
            key: value
            for key, value in {**details, "office_hours": weekday_hours()}.items()
            if key in field_names
        }
        Office.objects.filter(slug=slug).update(**updates)

    return report
