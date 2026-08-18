"""Seed the Onest org tree (head office → region → regional office → branch).

The listed markets are the locations Onest currently serves; they sit under
Mid-Atlantic and New England. Users pick an *assignable* office (head office,
a regional office that is itself a served market, or a branch).
"""


def upsert_office(
    office_model, *, slug, name, kind, parent=None, is_assignable=True, sort_order=0
):
    office, _ = office_model.objects.update_or_create(
        slug=slug,
        defaults={
            "name": name,
            "kind": kind,
            "parent": parent,
            "is_assignable": is_assignable,
            "is_active": True,
            "sort_order": sort_order,
        },
    )
    return office


def seed_offices(office_model=None):
    """Idempotent: safe to re-run. Returns the head office."""
    from apps.user.models import Office as LiveOffice

    Office = office_model or LiveOffice
    # String literals so this also runs against historical migration models
    # (they don't carry the Office.Kind enum).
    head_office = "head_office"
    region = "region"
    regional_office = "regional_office"
    branch = "branch"
    head = upsert_office(
        Office,
        slug="onest-head-office",
        name="Onest Real Estate",
        kind=head_office,
        is_assignable=True,
        sort_order=0,
    )

    mid_atlantic = upsert_office(
        Office,
        slug="region-mid-atlantic",
        name="Mid-Atlantic",
        kind=region,
        parent=head,
        is_assignable=False,
        sort_order=10,
    )
    new_england = upsert_office(
        Office,
        slug="region-new-england",
        name="New England",
        kind=region,
        parent=head,
        is_assignable=False,
        sort_order=20,
    )

    virginia = upsert_office(
        Office,
        slug="ro-virginia",
        name="Virginia",
        kind=regional_office,
        parent=mid_atlantic,
        is_assignable=False,
        sort_order=10,
    )
    upsert_office(
        Office,
        slug="charlottesville-va",
        name="Charlottesville VA",
        kind=branch,
        parent=virginia,
        sort_order=10,
    )
    upsert_office(
        Office,
        slug="fairfax-va",
        name="Fairfax VA",
        kind=branch,
        parent=virginia,
        sort_order=20,
    )

    upsert_office(
        Office,
        slug="district-of-columbia",
        name="District of Columbia",
        kind=regional_office,
        parent=mid_atlantic,
        sort_order=20,
    )
    upsert_office(
        Office,
        slug="maryland",
        name="Maryland",
        kind=regional_office,
        parent=mid_atlantic,
        sort_order=30,
    )

    pennsylvania = upsert_office(
        Office,
        slug="ro-pennsylvania",
        name="Pennsylvania",
        kind=regional_office,
        parent=mid_atlantic,
        is_assignable=False,
        sort_order=40,
    )
    upsert_office(
        Office,
        slug="harrisburg",
        name="Harrisburg",
        kind=branch,
        parent=pennsylvania,
        sort_order=10,
    )
    upsert_office(
        Office,
        slug="philadelphia",
        name="Philadelphia",
        kind=branch,
        parent=pennsylvania,
        sort_order=20,
    )
    upsert_office(
        Office,
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
            slug=slug,
            name=name,
            kind=regional_office,
            parent=new_england,
            sort_order=order,
        )

    return head
