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

from apps.user.models import Office, User, UserRoleAssignment
from apps.user.office_seed import SeedConflictError, seed_offices
from apps.user.roles import (
    ADMIN,
    AGENT,
    BRANCH_MANAGER,
    REGION_MANAGER,
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

    def __str__(self) -> str:
        return (
            "UserSeedReport("
            f"created={len(self.created)}, "
            f"matched={len(self.matched)}, "
            f"assignments_created={len(self.assignments_created)}, "
            f"assignments_matched={len(self.assignments_matched)})"
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
    if spec.scope_type != ScopeType.COMPANY:
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

    return report
