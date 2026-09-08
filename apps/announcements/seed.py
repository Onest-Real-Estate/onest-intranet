"""Demo announcements for local development.

Deliberately includes rows that the signed-in developer should **not** see —
another branch's notice, another region's news, a scheduled one, an expired
one. A seed that only produces visible rows makes an audience bug look like a
working feature, so the negatives are the point.

Idempotent: keyed on ``(owner_office, slug)``, so re-running updates the same
rows rather than accumulating copies. Audience selectors are rebuilt to match
the spec each run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.announcements.models import (
    Announcement,
    AnnouncementAudience,
    AnnouncementCategory,
)
from apps.announcements.taxonomy import (
    PRIORITY_IMPORTANT,
    PRIORITY_NORMAL,
    PRIORITY_URGENT,
)
from apps.user.models import Office, User

Kind = AnnouncementAudience.Kind


@dataclass(frozen=True)
class AudienceSpec:
    kind: str
    role: str = ""
    office_slug: str = ""
    #: For ``user`` selectors. Resolved at seed time; the selector is dropped
    #: with a note if that person has not been seeded, rather than failing the
    #: whole run over a demo row.
    user_email: str = ""


@dataclass(frozen=True)
class AnnouncementSpec:
    slug: str
    title: str
    summary: str
    body: str
    category_code: str
    priority: str
    owner_office_slug: str
    audience: tuple[AudienceSpec, ...]
    status: str = Announcement.Status.PUBLISHED
    #: Days relative to now. Negative is in the past.
    published_days_ago: int = 0
    publish_in_days: int | None = None
    expires_in_days: int | None = None


@dataclass
class AnnouncementSeedReport:
    created: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


SPECS: tuple[AnnouncementSpec, ...] = (
    # --- Reaches everyone ------------------------------------------------- #
    AnnouncementSpec(
        slug="mls-outage",
        title="MLS is down — use the paper backup for today's showings",
        summary="Vendor incident. Expected back this afternoon.",
        body=(
            "Our MLS provider reports a regional outage. Until it clears, log "
            "showings on the paper form at the front desk and enter them when "
            "service returns. No listing deadlines are affected."
        ),
        category_code="urgent_operational_notice",
        priority=PRIORITY_URGENT,
        owner_office_slug="onest-head-office",
        audience=(AudienceSpec(Kind.COMPANY),),
        published_days_ago=0,
    ),
    AnnouncementSpec(
        slug="q3-results",
        title="Q3 results and what they mean for the rest of the year",
        summary="Volume is up 6% year over year across the brokerage.",
        body=(
            "Closed volume rose 6% against the same quarter last year, led by "
            "the Mid-Atlantic region. Full figures and the regional breakdown "
            "are in the leadership deck."
        ),
        category_code="company_announcement",
        priority=PRIORITY_NORMAL,
        owner_office_slug="onest-head-office",
        audience=(AudienceSpec(Kind.COMPANY),),
        published_days_ago=4,
    ),
    # --- Region ------------------------------------------------------------ #
    AnnouncementSpec(
        slug="mid-atlantic-inventory",
        title="Mid-Atlantic inventory tightened again in August",
        summary="Weeks of supply fell to 1.8 across the region.",
        body=(
            "Months of supply is at its lowest since spring. Expect competing "
            "offers on well-priced listings; the regional pricing guidance has "
            "been updated to match."
        ),
        category_code="market_update",
        priority=PRIORITY_IMPORTANT,
        owner_office_slug="region-mid-atlantic",
        audience=(AudienceSpec(Kind.REGION, office_slug="region-mid-atlantic"),),
        published_days_ago=1,
    ),
    # --- Single office ----------------------------------------------------- #
    AnnouncementSpec(
        slug="fairfax-parking",
        title="Fairfax parking deck closed Saturday for resurfacing",
        summary="Street parking only from 6am to 6pm.",
        body=(
            "The deck is closed all day Saturday. Metered street parking is "
            "free at weekends; the side entrance stays badge-accessible."
        ),
        category_code="office_notice",
        priority=PRIORITY_NORMAL,
        owner_office_slug="fairfax-va",
        audience=(AudienceSpec(Kind.OFFICE, office_slug="fairfax-va"),),
        published_days_ago=2,
    ),
    # --- Role -------------------------------------------------------------- #
    AnnouncementSpec(
        slug="agency-disclosure-form",
        title="New agency disclosure form is mandatory from 1 September",
        summary="The old form will be rejected at closing.",
        body=(
            "Virginia has revised the agency disclosure. Use the new version "
            "for every agreement signed on or after 1 September; contracts "
            "already in flight may keep the old one."
        ),
        category_code="compliance_update",
        priority=PRIORITY_IMPORTANT,
        owner_office_slug="onest-head-office",
        audience=(AudienceSpec(Kind.ROLE, role="realtor"),),
        published_days_ago=3,
    ),
    AnnouncementSpec(
        slug="manager-training",
        title="Branch manager session: coaching the first ninety days",
        summary="Thursday, 10am, and recorded.",
        body=(
            "A working session on the first ninety days for new agents. Bring "
            "one case you are stuck on; the recording goes out on Friday."
        ),
        category_code="training_notice",
        priority=PRIORITY_NORMAL,
        owner_office_slug="onest-head-office",
        audience=(AudienceSpec(Kind.ROLE, role="branch_manager"),),
        published_days_ago=5,
    ),
    # --- Union: two selectors on one announcement -------------------------- #
    AnnouncementSpec(
        slug="new-crm-rollout",
        title="The new CRM reaches Fairfax and every regional manager",
        summary="Two audiences, one announcement — matching either is enough.",
        body=(
            "Fairfax is the pilot office, and regional managers are included "
            "so they can answer questions from the branches they cover. "
            "Matching either audience is enough to see this; nobody sees it "
            "twice."
        ),
        category_code="technology_notice",
        priority=PRIORITY_NORMAL,
        owner_office_slug="onest-head-office",
        audience=(
            AudienceSpec(Kind.OFFICE, office_slug="fairfax-va"),
            AudienceSpec(Kind.ROLE, role="regional_manager"),
        ),
        published_days_ago=6,
    ),
    # --- One named person -------------------------------------------------- #
    AnnouncementSpec(
        slug="fairfax-agent-welcome",
        title="Welcome to the Fairfax team",
        summary="Addressed to one person by name.",
        body=(
            "An individual selector: only the named recipient sees this, "
            "whatever office or role anyone else holds."
        ),
        category_code="company_announcement",
        priority=PRIORITY_NORMAL,
        owner_office_slug="fairfax-va",
        audience=(AudienceSpec(Kind.USER, user_email="agent.fairfax@onest.test"),),
        published_days_ago=7,
    ),
    # --- Deliberate negatives ---------------------------------------------- #
    AnnouncementSpec(
        slug="charlottesville-move",
        title="Charlottesville moves to the third floor",
        summary="Should NOT be visible to a Fairfax reader — sibling branch.",
        body="If you can see this from another branch, office scope is broken.",
        category_code="office_notice",
        priority=PRIORITY_URGENT,
        owner_office_slug="charlottesville-va",
        audience=(AudienceSpec(Kind.OFFICE, office_slug="charlottesville-va"),),
        published_days_ago=1,
    ),
    AnnouncementSpec(
        slug="new-england-market",
        title="New England market notes",
        summary="Should NOT be visible outside New England — other region.",
        body="If you can see this from the Mid-Atlantic, region scope is broken.",
        category_code="market_update",
        priority=PRIORITY_NORMAL,
        owner_office_slug="region-new-england",
        audience=(AudienceSpec(Kind.REGION, office_slug="region-new-england"),),
        published_days_ago=1,
    ),
    AnnouncementSpec(
        slug="fall-kickoff",
        title="Fall kickoff — save the date",
        summary="Should NOT be visible yet — scheduled for next week.",
        body="Scheduled announcement. Visible once its publish window opens.",
        category_code="event",
        priority=PRIORITY_URGENT,
        owner_office_slug="onest-head-office",
        audience=(AudienceSpec(Kind.COMPANY),),
        publish_in_days=7,
    ),
    AnnouncementSpec(
        slug="summer-picnic",
        title="Summer picnic — thanks for coming",
        summary="Should NOT be visible — expired last week.",
        body="Expired announcement. Retained for the record, out of the feed.",
        category_code="event",
        priority=PRIORITY_NORMAL,
        owner_office_slug="onest-head-office",
        audience=(AudienceSpec(Kind.COMPANY),),
        published_days_ago=30,
        expires_in_days=-7,
    ),
    # --- A draft carrying validation debt ---------------------------------- #
    AnnouncementSpec(
        slug="half-written-policy",
        title="Draft: revised referral policy",
        summary="A draft with outstanding validation debt.",
        body="",
        category_code="",
        priority="",
        owner_office_slug="onest-head-office",
        audience=(),
        status=Announcement.Status.DRAFT,
    ),
)


def _offset(days: int | None):
    return None if days is None else timezone.now() + timedelta(days=days)


@transaction.atomic
def seed_announcements() -> AnnouncementSeedReport:
    """Create or refresh the demo announcements. Safe to run repeatedly."""
    report = AnnouncementSeedReport()
    offices = {node.slug: node for node in Office.objects.all()}
    categories = {row.code: row for row in AnnouncementCategory.objects.all()}
    wanted_emails = {
        item.user_email for spec in SPECS for item in spec.audience if item.user_email
    }
    people = {row.email: row for row in User.objects.filter(email__in=wanted_emails)}

    for spec in SPECS:
        owner = offices.get(spec.owner_office_slug)
        if owner is None:
            # Offices are seeded separately; say so rather than half-seeding.
            report.skipped.append(f"{spec.slug} (missing office)")
            continue

        now = timezone.now()
        row, created = Announcement.objects.update_or_create(
            owner_office=owner,
            slug=spec.slug,
            defaults={
                "title": spec.title,
                "summary": spec.summary,
                "body": spec.body,
                "category": categories.get(spec.category_code),
                "priority": spec.priority,
                "status": spec.status,
                "publish_at": _offset(spec.publish_in_days),
                "expires_at": _offset(spec.expires_in_days),
                "published_at": (
                    None
                    if spec.status != Announcement.Status.PUBLISHED
                    else now - timedelta(days=spec.published_days_ago)
                ),
            },
        )

        # Rebuilt rather than merged, so removing a selector from the spec
        # actually removes it locally.
        AnnouncementAudience.objects.filter(announcement=row).delete()
        selectors = []
        for item in spec.audience:
            if item.user_email and item.user_email not in people:
                report.skipped.append(
                    f"{spec.slug} audience user {item.user_email} (not seeded)"
                )
                continue
            selectors.append(
                AnnouncementAudience(
                    announcement=row,
                    kind=item.kind,
                    role=item.role,
                    office=offices.get(item.office_slug) if item.office_slug else None,
                    user=people.get(item.user_email) if item.user_email else None,
                )
            )
        AnnouncementAudience.objects.bulk_create(selectors)
        (report.created if created else report.matched).append(spec.slug)

    return report
