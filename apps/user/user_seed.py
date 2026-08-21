"""Seed demo users with offices, display names, and role assignments.

Safe to re-run: users are keyed by email; live role assignments are matched
by (user, role, scope_type, scope_office). Profile fields are generated with
Faker (``en_US``) using a fixed seed so re-seeding stays deterministic.
Intended for local/dev databases via ``manage.py seed_users``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone
from faker import Faker

from apps.user.models import Office, OfficeContactAssignment, User, UserRoleAssignment
from apps.user.office_seed import SeedConflictError, seed_offices
from apps.user.roles import (
    ACCOUNTANT,
    ADMIN,
    AGENT,
    BRANCH_ADMIN,
    BRANCH_MANAGER,
    BROKER_ADMIN,
    IT_SUPPORT,
    MARKETING_TEAM,
    PRINCIPAL_BROKER,
    REGION_MANAGER,
    REGIONAL_ADMIN,
    REGIONAL_TRANSACTION_COORDINATOR,
    TRANSACTION_COORDINATOR,
    ScopeType,
    role_group_name,
    seed_role_groups,
)

DEFAULT_FAKER_SEED = 42


@dataclass
class UserSeedReport:
    created: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)
    assignments_created: list[str] = field(default_factory=list)
    assignments_matched: list[str] = field(default_factory=list)
    contacts_created: list[str] = field(default_factory=list)
    contacts_matched: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            "UserSeedReport("
            f"created={len(self.created)}, "
            f"matched={len(self.matched)}, "
            f"assignments_created={len(self.assignments_created)}, "
            f"assignments_matched={len(self.assignments_matched)}, "
            f"contacts_created={len(self.contacts_created)}, "
            f"contacts_matched={len(self.contacts_matched)})"
        )


@dataclass(frozen=True)
class UserSeedSpec:
    email: str
    first_name: str
    last_name: str
    display_name: str
    office_slug: str
    phone_number: str = ""
    street_address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    role: str | None = None
    scope_type: str | None = None
    scope_office_slug: str | None = None
    is_superuser: bool = False
    is_staff: bool = False


@dataclass(frozen=True)
class UserSeedTemplate:
    email: str
    office_slug: str
    role: str | None = None
    scope_type: str | None = None
    scope_office_slug: str | None = None
    is_superuser: bool = False
    is_staff: bool = False


DEV_USER_TEMPLATES: tuple[UserSeedTemplate, ...] = (
    UserSeedTemplate(
        email="superadmin@onest.test",
        office_slug="onest-head-office",
        is_superuser=True,
        is_staff=True,
    ),
    UserSeedTemplate(
        email="admin@onest.test",
        office_slug="onest-head-office",
        role=ADMIN,
        scope_type=ScopeType.COMPANY,
    ),
    UserSeedTemplate(
        email="region.midatlantic@onest.test",
        office_slug="charlottesville-va",
        role=REGION_MANAGER,
        scope_type=ScopeType.REGION,
        scope_office_slug="region-mid-atlantic",
    ),
    UserSeedTemplate(
        email="branch.charlottesville@onest.test",
        office_slug="charlottesville-va",
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office_slug="charlottesville-va",
    ),
    UserSeedTemplate(
        email="agent.charlottesville@onest.test",
        office_slug="charlottesville-va",
        role=AGENT,
        scope_type=ScopeType.OFFICE,
        scope_office_slug="charlottesville-va",
    ),
    UserSeedTemplate(
        email="agent.fairfax@onest.test",
        office_slug="fairfax-va",
        role=AGENT,
        scope_type=ScopeType.OFFICE,
        scope_office_slug="fairfax-va",
    ),
    UserSeedTemplate(
        email="agent.connecticut@onest.test",
        office_slug="connecticut",
        role=AGENT,
        scope_type=ScopeType.OFFICE,
        scope_office_slug="connecticut",
    ),
)


def _profile_from_faker(fake: Faker) -> dict[str, str]:
    first_name = fake.first_name()
    last_name = fake.last_name()
    return {
        "first_name": first_name,
        "last_name": last_name,
        "display_name": f"{first_name} {last_name}",
        "phone_number": fake.numerify("(###) 555-####"),
        "street_address": fake.street_address(),
        "city": fake.city(),
        "state": fake.state_abbr(),
        "zip_code": fake.zipcode(),
    }


def build_user_specs(
    templates: tuple[UserSeedTemplate, ...] = DEV_USER_TEMPLATES,
    *,
    seed: int = DEFAULT_FAKER_SEED,
) -> tuple[UserSeedSpec, ...]:
    """Build user specs with Faker-generated names and profile fields."""
    fake = Faker("en_US")
    fake.seed_instance(seed)
    specs: list[UserSeedSpec] = []
    for template in templates:
        profile = _profile_from_faker(fake)
        specs.append(
            UserSeedSpec(
                email=template.email,
                office_slug=template.office_slug,
                role=template.role,
                scope_type=template.scope_type,
                scope_office_slug=template.scope_office_slug,
                is_superuser=template.is_superuser,
                is_staff=template.is_staff,
                **profile,
            )
        )
    return tuple(specs)


DEV_USER_SPECS = build_user_specs()


@dataclass(frozen=True)
class StaffSeedSpec:
    """Real oNEST staff member seeded with their verified directory data."""

    email: str
    first_name: str
    last_name: str
    display_name: str
    office_slug: str
    phone_number: str = ""
    role: str | None = None
    scope_type: str | None = None
    scope_office_slug: str | None = None


# The ONEST Regional Offices directory. Roma Osti's email is not shown in the
# directory; roma@onest.realestate follows the established pattern but should
# be verified before production use.
STAFF_SEED_SPECS: tuple[StaffSeedSpec, ...] = (
    # Branch managers — one per served market.
    StaffSeedSpec(
        email="suman@onest.realestate",
        first_name="Suman",
        last_name="Mahara",
        display_name="Suman Mahara",
        office_slug="massachusetts",
        phone_number="(857) 869-2765",
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office_slug="massachusetts",
    ),
    StaffSeedSpec(
        email="bishwa@onest.realestate",
        first_name="Bishwa",
        last_name="Chhetri",
        display_name="Bishwa Chhetri",
        office_slug="harrisburg",
        phone_number="(730) 608-9412",
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office_slug="harrisburg",
    ),
    StaffSeedSpec(
        email="srai@onest.realestate",
        first_name="Sancha Man",
        last_name="Rai",
        display_name="Sancha Man Rai",
        office_slug="pittsburgh",
        phone_number="(412) 515-1429",
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office_slug="pittsburgh",
    ),
    StaffSeedSpec(
        email="malladhakal@onest.realestate",
        first_name="Raju Malla",
        last_name="Dhakal",
        display_name="Raju Malla Dhakal",
        office_slug="philadelphia",
        phone_number="(551) 254-0620",
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office_slug="philadelphia",
    ),
    StaffSeedSpec(
        email="chiran@onest.realestate",
        first_name="Chiran",
        last_name="Neupane",
        display_name="Chiran Neupane",
        office_slug="connecticut",
        phone_number="(617) 229-9883",
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office_slug="connecticut",
    ),
    StaffSeedSpec(
        email="ranjan@onest.realestate",
        first_name="Ranjan",
        last_name="Budhathoki",
        display_name="Ranjan Budhathoki",
        office_slug="new-hampshire",
        phone_number="(617) 319-9541",
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office_slug="new-hampshire",
    ),
    StaffSeedSpec(
        email="prashanna@onest.realestate",
        first_name="Prashanna",
        last_name="Sangroula",
        display_name="Prashanna Sangroula",
        office_slug="charlottesville-va",
        phone_number="(571) 222-5555",
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office_slug="charlottesville-va",
    ),
    # Executive leadership.
    StaffSeedSpec(
        email="info@onest.realestate",
        first_name="Anjana",
        last_name="Budhathoki",
        display_name="Anjana Budhathoki",
        office_slug="onest-head-office",
        phone_number="(703) 509-1167",
        role=PRINCIPAL_BROKER,
        scope_type=ScopeType.COMPANY,
    ),
    StaffSeedSpec(
        email="suresh@onest.realestate",
        first_name="Suresh",
        last_name="Sapkota",
        display_name="Suresh Sapkota",
        office_slug="onest-head-office",
        phone_number="(703) 509-1127",
        role=BROKER_ADMIN,
        scope_type=ScopeType.COMPANY,
    ),
    # Specialized support / corporate directory.
    StaffSeedSpec(
        email="soni@onest.realestate",
        first_name="Soni",
        last_name="Rajlawat",
        display_name="Soni Rajlawat",
        office_slug="onest-head-office",
        phone_number="+977-981-830-4967",
        role=REGIONAL_TRANSACTION_COORDINATOR,
        scope_type=ScopeType.ASSIGNED_RECORD,
    ),
    StaffSeedSpec(
        email="anushree@onest.realestate",
        first_name="Anushree",
        last_name="Rajlawat",
        display_name="Anushree Rajlawat",
        office_slug="onest-head-office",
        role=TRANSACTION_COORDINATOR,
        scope_type=ScopeType.ASSIGNED_RECORD,
    ),
    # Marketing manager's name is not shown in the directory; the shared
    # inbox is used as identity until a named owner is confirmed.
    StaffSeedSpec(
        email="marketing@onest.realestate",
        first_name="oNEST",
        last_name="Marketing",
        display_name="oNEST Marketing",
        office_slug="onest-head-office",
        role=MARKETING_TEAM,
        scope_type=ScopeType.COMPANY,
    ),
    StaffSeedSpec(
        email="sid@onest.realestate",
        first_name="Siddhartha",
        last_name="Khanal",
        display_name="Siddhartha Khanal",
        office_slug="onest-head-office",
        role=IT_SUPPORT,
        scope_type=ScopeType.COMPANY,
    ),
    StaffSeedSpec(
        email="pratik@onest.realestate",
        first_name="Pratik",
        last_name="Bhusal",
        display_name="Pratik Bhusal",
        office_slug="onest-head-office",
        phone_number="(571) 326-8003",
        role=IT_SUPPORT,
        scope_type=ScopeType.COMPANY,
    ),
    StaffSeedSpec(
        email="support@onest.realestate",
        first_name="David",
        last_name="Basnet",
        display_name="David Basnet",
        office_slug="onest-head-office",
        phone_number="+977-9823416819",
        role=IT_SUPPORT,
        scope_type=ScopeType.COMPANY,
    ),
    StaffSeedSpec(
        email="accounting@onest.realestate",
        first_name="Nirvana",
        last_name="Budhathoki",
        display_name="Nirvana Budhathoki",
        office_slug="onest-head-office",
        phone_number="+9953706857",
        role=ACCOUNTANT,
        scope_type=ScopeType.COMPANY,
    ),
    # Regional admins (coverage areas per the directory).
    StaffSeedSpec(
        email="admin@onest.realestate",
        first_name="Bashu",
        last_name="Aryal",
        display_name="Bashu Aryal",
        office_slug="charlottesville-va",
        phone_number="(812) 399-2341",
        role=BRANCH_ADMIN,
        scope_type=ScopeType.OFFICE,
        scope_office_slug="charlottesville-va",
    ),
    StaffSeedSpec(
        email="nh@onest.realestate",
        first_name="Manoja",
        last_name="Pakhrin",
        display_name="Manoja Pakhrin",
        office_slug="massachusetts",
        phone_number="(603) 514-8027",
        role=REGIONAL_ADMIN,
        scope_type=ScopeType.REGION,
        scope_office_slug="region-new-england",
    ),
    StaffSeedSpec(
        email="roma@onest.realestate",
        first_name="Roma",
        last_name="Osti",
        display_name="Roma Osti",
        office_slug="harrisburg",
        phone_number="(717) 306-6315",
        role=REGIONAL_ADMIN,
        scope_type=ScopeType.REGION,
        scope_office_slug="region-mid-atlantic",
    ),
)

BRANCH_OFFICE_SLUGS: tuple[str, ...] = (
    "massachusetts",
    "harrisburg",
    "pittsburgh",
    "philadelphia",
    "connecticut",
    "new-hampshire",
    "charlottesville-va",
)


@dataclass(frozen=True)
class ContactCoverageSpec:
    """Contact assignment coverage: one staff member across many offices."""

    email: str
    assignment_type: str
    office_slugs: tuple[str, ...]
    is_primary: bool = True


def _contact_coverage() -> tuple[ContactCoverageSpec, ...]:
    types = OfficeContactAssignment.AssignmentType
    return (
        *(
            ContactCoverageSpec(spec.email, types.MANAGER, (spec.office_slug,))
            for spec in STAFF_SEED_SPECS
            if spec.role == BRANCH_MANAGER
        ),
        ContactCoverageSpec(
            "admin@onest.realestate",
            types.ADMIN,
            ("charlottesville-va", "fairfax-va"),
        ),
        ContactCoverageSpec(
            "nh@onest.realestate",
            types.ADMIN,
            ("massachusetts", "connecticut", "new-hampshire", "rhode-island"),
        ),
        ContactCoverageSpec(
            "roma@onest.realestate",
            types.ADMIN,
            ("harrisburg", "philadelphia", "pittsburgh"),
        ),
        ContactCoverageSpec(
            "anushree@onest.realestate",
            types.TRANSACTION_COORDINATOR,
            BRANCH_OFFICE_SLUGS,
        ),
        ContactCoverageSpec(
            "pratik@onest.realestate", types.IT_SUPPORT, BRANCH_OFFICE_SLUGS
        ),
        ContactCoverageSpec(
            "info@onest.realestate", types.PRINCIPAL_BROKER, ("onest-head-office",)
        ),
        ContactCoverageSpec(
            "suresh@onest.realestate", types.ASSOCIATE_BROKER, ("onest-head-office",)
        ),
        ContactCoverageSpec(
            "soni@onest.realestate", types.TC_MANAGER, ("onest-head-office",)
        ),
        ContactCoverageSpec(
            "marketing@onest.realestate",
            types.MARKETING_MANAGER,
            ("onest-head-office",),
        ),
        ContactCoverageSpec(
            "sid@onest.realestate", types.IT_MANAGER, ("onest-head-office",)
        ),
        ContactCoverageSpec(
            "pratik@onest.realestate", types.IT_SUPPORT, ("onest-head-office",)
        ),
        ContactCoverageSpec(
            "support@onest.realestate",
            types.IT_SUPPORT,
            ("onest-head-office",),
            is_primary=False,
        ),
        ContactCoverageSpec(
            "accounting@onest.realestate", types.ACCOUNTING, ("onest-head-office",)
        ),
    )


def _resolve_office(slug: str) -> Office:
    try:
        return Office.objects.get(slug=slug)
    except Office.DoesNotExist as exc:
        raise RuntimeError(
            f"Office slug '{slug}' is missing. Run seed_offices first."
        ) from exc


def _upsert_user(
    report: UserSeedReport,
    spec: UserSeedSpec,
    *,
    password: str,
) -> User:
    office = _resolve_office(spec.office_slug)
    defaults = {
        "first_name": spec.first_name,
        "last_name": spec.last_name,
        "display_name": spec.display_name,
        "phone_number": spec.phone_number,
        "street_address": spec.street_address,
        "city": spec.city,
        "state": spec.state,
        "zip_code": spec.zip_code,
        "office": office,
        "profile_completed": True,
        "profile_completed_at": timezone.now(),
        "is_superuser": spec.is_superuser,
        "is_staff": spec.is_staff or spec.is_superuser,
    }
    user, created = User.objects.get_or_create(email=spec.email, defaults=defaults)
    if created:
        user.set_password(password)
        user.save()
        report.created.append(spec.email)
        return user

    updates = {
        "first_name": spec.first_name,
        "last_name": spec.last_name,
        "display_name": spec.display_name,
        "phone_number": spec.phone_number,
        "street_address": spec.street_address,
        "city": spec.city,
        "state": spec.state,
        "zip_code": spec.zip_code,
        "office": office,
        "profile_completed": True,
        "is_staff": spec.is_staff or spec.is_superuser,
    }
    if not user.profile_completed_at:
        updates["profile_completed_at"] = timezone.now()
    User.objects.filter(pk=user.pk).update(**updates)
    user.refresh_from_db()
    report.matched.append(spec.email)
    return user


def _ensure_role_assignment(
    report: UserSeedReport,
    user: User,
    spec: UserSeedSpec,
) -> None:
    if spec.role is None or spec.scope_type is None:
        return

    scope_office = None
    if spec.scope_type not in ScopeType.ORG_LESS:
        slug = spec.scope_office_slug or spec.office_slug
        scope_office = _resolve_office(slug)

    label = f"{spec.email}:{spec.role}:{spec.scope_type}"
    existing = UserRoleAssignment.objects.filter(
        user=user,
        role=spec.role,
        scope_type=spec.scope_type,
        scope_office=scope_office,
        status__in=[
            UserRoleAssignment.Status.SCHEDULED,
            UserRoleAssignment.Status.ACTIVE,
        ],
    ).first()
    if existing is None:
        assignment = UserRoleAssignment(
            user=user,
            role=spec.role,
            scope_type=spec.scope_type,
            scope_office=scope_office,
        )
        assignment.refresh_status()
        assignment.full_clean()
        assignment.save()
        report.assignments_created.append(label)
    else:
        report.assignments_matched.append(label)

    group, _ = Group.objects.get_or_create(name=role_group_name(spec.role))
    user.groups.add(group)


def _staff_to_seed_spec(spec: StaffSeedSpec) -> UserSeedSpec:
    return UserSeedSpec(
        email=spec.email,
        first_name=spec.first_name,
        last_name=spec.last_name,
        display_name=spec.display_name,
        office_slug=spec.office_slug,
        phone_number=spec.phone_number,
        role=spec.role,
        scope_type=spec.scope_type,
        scope_office_slug=spec.scope_office_slug,
    )


def _ensure_contact_coverage(report: UserSeedReport) -> None:
    """Wire OfficeContactAssignment rows for the staff directory.

    ``create()`` deliberately skips ``full_clean()``: coverage roles
    (regional admins, company-wide TCs and IT support) legitimately span
    offices beyond the holder's seat, which the model's same-office check
    rejects. The database still enforces the uniqueness constraints.
    """
    offices_by_slug = dict(Office.objects.values_list("slug", "pk"))
    users_by_email = {
        user.email: user
        for user in User.objects.filter(
            email__in={spec.email for spec in _contact_coverage()}
        )
    }
    for coverage in _contact_coverage():
        user = users_by_email.get(coverage.email)
        if user is None:
            raise RuntimeError(
                f"Staff user '{coverage.email}' is missing. Seed staff first."
            )
        for slug in coverage.office_slugs:
            office_pk = offices_by_slug.get(slug)
            if office_pk is None:
                raise RuntimeError(
                    f"Office slug '{slug}' is missing. Run seed_offices first."
                )
            label = f"{coverage.email}:{coverage.assignment_type}:{slug}"
            exists = OfficeContactAssignment.objects.filter(
                office_id=office_pk,
                user=user,
                assignment_type=coverage.assignment_type,
            ).exists()
            if exists:
                report.contacts_matched.append(label)
                continue
            OfficeContactAssignment.objects.create(
                office_id=office_pk,
                user=user,
                assignment_type=coverage.assignment_type,
                is_primary=coverage.is_primary,
            )
            report.contacts_created.append(label)


def seed_staff(*, password: str = "onest-dev-seed") -> UserSeedReport:
    """Idempotent real-staff seed: directory users + contact assignments."""
    report = UserSeedReport()
    with transaction.atomic():
        for spec in STAFF_SEED_SPECS:
            user = _upsert_user(report, _staff_to_seed_spec(spec), password=password)
            _ensure_role_assignment(report, user, _staff_to_seed_spec(spec))
        _ensure_contact_coverage(report)
    return report


def seed_users(
    *,
    password: str = "onest-dev-seed",
    specs: tuple[UserSeedSpec, ...] | None = None,
    faker_seed: int = DEFAULT_FAKER_SEED,
    ensure_prerequisites: bool = True,
) -> UserSeedReport:
    """Idempotent demo users for local development."""
    if specs is None:
        specs = build_user_specs(seed=faker_seed)

    report = UserSeedReport()
    if ensure_prerequisites:
        office_report = seed_offices()
        if office_report.conflicting:
            raise SeedConflictError(
                f"Office seed conflicts: {office_report.conflicting}"
            )
        seed_role_groups()

    with transaction.atomic():
        for spec in specs:
            user = _upsert_user(report, spec, password=password)
            _ensure_role_assignment(report, user, spec)

    staff_report = seed_staff(password=password)
    report.created.extend(
        email for email in staff_report.created if email not in report.created
    )
    report.matched.extend(
        email for email in staff_report.matched if email not in report.matched
    )
    report.assignments_created.extend(staff_report.assignments_created)
    report.assignments_matched.extend(staff_report.assignments_matched)
    report.contacts_created = staff_report.contacts_created
    report.contacts_matched = staff_report.contacts_matched
    return report
