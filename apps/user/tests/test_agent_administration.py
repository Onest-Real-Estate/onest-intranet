"""Broker-controlled profile administration.

The matrix these tests care about is role × scope × target user, plus the four
ways the surface could leak: a crafted POST, a stale permission cache, a
concurrent edit, and an administrative value reaching the self-service form.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.roles import ADMIN, AGENT, BRANCH_MANAGER, REGION_MANAGER, ScopeType
from apps.user.services.agent_administration import (
    administered_user_queryset,
    administration_version,
    can_change_administration,
    delegable_role_options,
    grant_role_assignment,
    invalidate_permission_cache,
    revoke_role_assignment_for_user,
    update_administration,
)
from apps.user.services.role_assignments import get_effective_access
from apps.user.tests.test_onboarding import valid_profile_post
from apps.user.tests.test_profile import completed_user, valid_self_profile_post

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAIRFAX = "fairfax-va"
CHARLOTTESVILLE = "charlottesville-va"
MID_ATLANTIC = "region-mid-atlantic"
NEW_ENGLAND = "region-new-england"
CONNECTICUT = "connecticut"


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def assign(user: User, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def agent_in(slug: str, email: str = "agent@example.com") -> User:
    user = completed_user(email=email, office=office(slug))
    assign(user, AGENT, ScopeType.OFFICE, office(slug))
    return user


def company_admin(email: str = "admin@example.com") -> User:
    user = completed_user(email=email, office=office(FAIRFAX))
    assign(user, ADMIN, ScopeType.COMPANY)
    return user


def branch_manager(slug: str = FAIRFAX, email: str = "branch@example.com") -> User:
    user = completed_user(email=email, office=office(slug))
    assign(user, BRANCH_MANAGER, ScopeType.OFFICE, office(slug))
    return user


def region_manager(
    region_slug: str = MID_ATLANTIC,
    seat: str = FAIRFAX,
    email: str = "region@example.com",
) -> User:
    user = completed_user(email=email, office=office(seat))
    assign(user, REGION_MANAGER, ScopeType.REGION, office(region_slug))
    return user


def admin_post(target: User, **overrides) -> dict:
    assert target.office is not None
    data = {
        "expected_version": administration_version(target),
        "office": str(target.office.pk),
        "agent_status": "active",
        "start_date": "",
        "agent_identifier": "",
        "license_verification_state": "unverified",
        "license_verification_note": "",
        "internal_notes": "",
    }
    data.update(overrides)
    return data


def props(response) -> dict:
    return json.loads(response.content)["props"]


def page(client, target: User) -> dict:
    response = client.get(
        reverse("user_administration", args=[target.pk]), HTTP_X_INERTIA="true"
    )
    assert response.status_code == 200
    return props(response)["administration"]


# ---------------------------------------------------------------------------
# Authorization matrix: role × scope × target
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_administration_requires_authentication(client):
    target = agent_in(FAIRFAX)
    response = client.get(reverse("user_administration", args=[target.pk]))
    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_plain_agent_cannot_reach_the_administration_page(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    actor = agent_in(FAIRFAX, email="nosy@example.com")
    client.force_login(actor)
    response = client.get(reverse("user_administration", args=[target.pk]))
    assert response.status_code == 403


@pytest.mark.django_db
def test_company_admin_may_administer_anybody(client):
    target = agent_in(CONNECTICUT, email="target@example.com")
    client.force_login(company_admin())
    payload = page(client, target)
    assert payload["subject"]["email"] == "target@example.com"
    assert payload["editable"]["administration"] is True


@pytest.mark.django_db
def test_branch_manager_may_administer_their_own_office(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(branch_manager(FAIRFAX))
    payload = page(client, target)
    assert payload["editable"]["administration"] is True


@pytest.mark.django_db
def test_branch_manager_cannot_reach_another_office(client):
    target = agent_in(CHARLOTTESVILLE, email="target@example.com")
    client.force_login(branch_manager(FAIRFAX))
    response = client.get(reverse("user_administration", args=[target.pk]))
    # 404 rather than 403: confirming the id exists is itself a disclosure.
    assert response.status_code == 404


@pytest.mark.django_db
def test_region_manager_reaches_every_office_in_their_region(client):
    fairfax = agent_in(FAIRFAX, email="fairfax@example.com")
    charlottesville = agent_in(CHARLOTTESVILLE, email="cville@example.com")
    client.force_login(region_manager(MID_ATLANTIC))
    assert page(client, fairfax)["subject"]["email"] == "fairfax@example.com"
    assert page(client, charlottesville)["subject"]["email"] == "cville@example.com"


@pytest.mark.django_db
def test_region_manager_cannot_reach_another_region(client):
    target = agent_in(CONNECTICUT, email="target@example.com")
    client.force_login(region_manager(MID_ATLANTIC))
    response = client.get(reverse("user_administration", args=[target.pk]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_an_actor_with_two_roles_gets_the_union_of_their_scopes():
    """Multiple roles widen scope; they never narrow it."""
    actor = completed_user(email="both@example.com", office=office(FAIRFAX))
    assign(actor, BRANCH_MANAGER, ScopeType.OFFICE, office(FAIRFAX))
    assign(actor, REGION_MANAGER, ScopeType.REGION, office(NEW_ENGLAND))
    agent_in(FAIRFAX, email="a@example.com")
    agent_in(CONNECTICUT, email="b@example.com")
    out_of_scope = agent_in(CHARLOTTESVILLE, email="c@example.com")

    reachable = set(administered_user_queryset(actor).values_list("email", flat=True))
    assert {"a@example.com", "b@example.com"} <= reachable
    assert out_of_scope.email not in reachable


@pytest.mark.django_db
def test_a_user_without_an_office_is_reachable_only_company_wide():
    stranded = completed_user(email="stranded@example.com", office=None)
    assert stranded in administered_user_queryset(company_admin())
    assert stranded not in administered_user_queryset(branch_manager(FAIRFAX))


# ---------------------------------------------------------------------------
# Privilege escalation and self-promotion
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_nobody_administers_their_own_record(client):
    actor = company_admin()
    client.force_login(actor)
    payload = page(client, actor)
    assert payload["subject"]["isSelf"] is True
    assert payload["editable"]["administration"] is False

    response = client.post(
        reverse("user_administration_submit", args=[actor.pk]),
        admin_post(actor, agent_status="departed"),
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_superuser_cannot_administer_their_own_record():
    root = User.objects.create_superuser(email="root@example.com", password="x")
    assert can_change_administration(root, root) is False


@pytest.mark.django_db
def test_crafted_post_cannot_set_account_or_role_fields(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(company_admin())
    response = client.post(
        reverse("user_administration_submit", args=[target.pk]),
        admin_post(
            target,
            is_superuser="1",
            is_staff="1",
            is_active="0",
            groups="1",
            email="hijacked@example.com",
            role="Admins",
            license_number="FORGED",
        ),
    )
    assert response.status_code == 302
    target.refresh_from_db()
    assert target.is_superuser is False
    assert target.is_staff is False
    assert target.is_active is True
    assert target.email == "target@example.com"
    # The license number belongs to the agent, not to this form.
    assert target.license_number == ""


@pytest.mark.django_db
def test_branch_manager_cannot_move_a_user_out_of_their_scope(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(branch_manager(FAIRFAX))
    response = client.post(
        reverse("user_administration_submit", args=[target.pk]),
        admin_post(target, office=str(office(CONNECTICUT).pk)),
    )
    assert response.status_code == 422
    target.refresh_from_db()
    assert target.office == office(FAIRFAX)


@pytest.mark.django_db
def test_office_choices_never_exceed_the_actors_scope(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(branch_manager(FAIRFAX))
    offered = {item["id"] for item in page(client, target)["options"]["offices"]}
    assert offered == {office(FAIRFAX).pk}


@pytest.mark.django_db
def test_scoped_manager_may_not_delegate_any_role(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    actor = branch_manager(FAIRFAX)
    assert delegable_role_options(actor) == []

    client.force_login(actor)
    response = client.post(
        reverse("user_administration_roles", args=[target.pk]),
        {
            "action": "grant",
            "role": BRANCH_MANAGER,
            "scope_type": ScopeType.OFFICE,
            "scope_office": str(office(FAIRFAX).pk),
            "business_reason": "Promotion",
        },
    )
    assert response.status_code == 422
    assert not UserRoleAssignment.objects.filter(
        user=target, role=BRANCH_MANAGER
    ).exists()


@pytest.mark.django_db
def test_the_admin_role_is_never_delegable():
    actor = company_admin()
    offered = {option["value"] for option in delegable_role_options(actor)}
    assert ADMIN not in offered

    target = agent_in(FAIRFAX, email="target@example.com")
    with pytest.raises(PermissionDenied):
        grant_role_assignment(
            actor=actor,
            target=target,
            role=ADMIN,
            scope_type=ScopeType.COMPANY,
            scope_office=None,
            business_reason="Escalation attempt",
        )


@pytest.mark.django_db
def test_granting_a_role_outside_the_delegation_boundary_is_refused():
    """Even a hand-built call cannot name an office the actor does not hold."""
    actor = region_manager(MID_ATLANTIC)
    assign(actor, ADMIN, ScopeType.COMPANY)
    # ``ADMIN`` makes the actor company-wide, so narrow the check to a user the
    # region manager alone could not reach.
    target = agent_in(CONNECTICUT, email="target@example.com")
    assert can_change_administration(actor, target) is True

    plain = region_manager(MID_ATLANTIC, email="plain@example.com")
    with pytest.raises(PermissionDenied):
        grant_role_assignment(
            actor=plain,
            target=target,
            role=AGENT,
            scope_type=ScopeType.OFFICE,
            scope_office=office(CONNECTICUT),
            business_reason="Out of region",
        )


# ---------------------------------------------------------------------------
# The agent's own view: readable, never writable
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_profile_shows_the_administrative_record_read_only(client):
    user = agent_in(FAIRFAX, email="agent@example.com")
    user.agent_status = "on_leave"
    user.agent_identifier = "ON-4412"
    user.start_date = timezone.localdate()
    user.save()

    client.force_login(user)
    identity = props(client.get(reverse("profile"), HTTP_X_INERTIA="true"))["identity"]
    administrative = identity["administrative"]
    assert administrative["agentStatus"]["value"] == "on_leave"
    assert administrative["agentIdentifier"] == "ON-4412"
    assert administrative["contractStatus"]["available"] is False
    assert "internalNotes" not in administrative


@pytest.mark.django_db
def test_operational_notes_never_reach_the_agent(client):
    user = agent_in(FAIRFAX, email="agent@example.com")
    user.internal_notes = "Escalated compensation dispute, do not discuss."
    user.save()
    client.force_login(user)
    response = client.get(reverse("profile"), HTTP_X_INERTIA="true")
    assert b"compensation dispute" not in response.content


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field",
    [
        "agent_status",
        "start_date",
        "agent_identifier",
        "internal_notes",
        "license_verification_state",
        "license_verification_note",
        "administration_updated_at",
        "license_verified_by",
    ],
)
def test_profile_submit_rejects_every_administrative_field(client, field):
    user = agent_in(FAIRFAX, email="agent@example.com")
    client.force_login(user)
    response = client.post(
        reverse("profile_submit"), valid_self_profile_post(**{field: "x"})
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_editing_a_license_returns_it_to_unverified(client):
    user = agent_in(FAIRFAX, email="agent@example.com")
    admin = company_admin()
    user.license_number = "VA-1"
    user.save()
    update_administration(
        actor=admin,
        target=user,
        cleaned={"license_verification_state": "verified"},
        expected_version="",
    )
    user.refresh_from_db()
    assert user.license_verification_state == "verified"
    assert user.license_verified_by == admin

    client.force_login(user)
    response = client.post(
        reverse("profile_submit"), valid_self_profile_post(license_number="VA-2")
    )
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.license_number == "VA-2"
    assert user.license_verification_state == "unverified"
    assert user.license_verified_at is None
    assert AuditEvent.objects.filter(action="user.license_verification.reset").exists()


@pytest.mark.django_db
def test_an_unrelated_profile_save_leaves_the_verification_alone(client):
    user = agent_in(FAIRFAX, email="agent@example.com")
    user.license_number = "VA-1"
    user.license_state = "VA"
    user.license_expires_on = dt.date(2030, 6, 30)
    user.save()
    update_administration(
        actor=company_admin(),
        target=user,
        cleaned={"license_verification_state": "verified"},
        expected_version="",
    )

    client.force_login(user)
    response = client.post(
        reverse("profile_submit"),
        valid_self_profile_post(license_number="VA-1", bio="A new bio."),
    )
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.license_verification_state == "verified"


# ---------------------------------------------------------------------------
# Persistence, provenance, and audit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_administration_update_persists_and_records_provenance(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    actor = company_admin()
    client.force_login(actor)
    response = client.post(
        reverse("user_administration_submit", args=[target.pk]),
        admin_post(
            target,
            agent_status="on_leave",
            start_date="2024-03-01",
            agent_identifier="on-4412",
            internal_notes="Parental leave until October.",
        ),
    )
    assert response.status_code == 302
    target.refresh_from_db()
    assert target.agent_status == "on_leave"
    assert target.start_date == dt.date(2024, 3, 1)
    assert target.agent_identifier == "ON-4412"
    assert target.internal_notes.startswith("Parental leave")
    assert target.administration_updated_by == actor
    assert target.administration_updated_at is not None


@pytest.mark.django_db
def test_a_successful_change_is_audited_with_before_and_after(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(company_admin())
    client.post(
        reverse("user_administration_submit", args=[target.pk]),
        admin_post(target, agent_status="suspended"),
    )
    event = AuditEvent.objects.filter(action="user.administration.updated").latest(
        "occurred_at"
    )
    assert event.outcome == AuditEvent.Outcome.SUCCESS
    assert event.target_id == str(target.pk)
    assert event.changes["agent_status"] == {"before": "active", "after": "suspended"}
    assert event.actor_label == "admin@example.com"


@pytest.mark.django_db
def test_operational_notes_are_never_written_into_the_audit_trail(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(company_admin())
    client.post(
        reverse("user_administration_submit", args=[target.pk]),
        admin_post(target, internal_notes="Under investigation by compliance."),
    )
    event = AuditEvent.objects.filter(action="user.administration.updated").latest(
        "occurred_at"
    )
    serialized = json.dumps([event.before, event.after, event.changes])
    assert "investigation" not in serialized
    assert event.after["internal_notes_present"] is True


@pytest.mark.django_db
def test_a_denied_change_is_audited(client):
    target = agent_in(CONNECTICUT, email="target@example.com")
    actor = company_admin()
    with pytest.raises(PermissionDenied):
        update_administration(
            actor=actor,
            target=actor,
            cleaned={"agent_status": "departed"},
            expected_version="",
        )
    event = AuditEvent.objects.filter(
        action="security.user_administration.denied"
    ).latest("occurred_at")
    assert event.outcome == AuditEvent.Outcome.DENIED
    assert event.reason == "self_administration"
    assert target.agent_status == "active"


# ---------------------------------------------------------------------------
# Access recalculation and cached permissions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_moving_office_retires_the_stale_agent_assignment(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(company_admin())
    client.post(
        reverse("user_administration_submit", args=[target.pk]),
        admin_post(target, office=str(office(CHARLOTTESVILLE).pk)),
    )
    target.refresh_from_db()
    assert target.office == office(CHARLOTTESVILLE)
    live = UserRoleAssignment.objects.filter(
        user=target, role=AGENT, status__in=["scheduled", "active"]
    )
    assert [item.scope_office for item in live] == [office(CHARLOTTESVILLE)]
    assert get_effective_access(target).office_keys == frozenset({CHARLOTTESVILLE})


@pytest.mark.django_db
def test_invalidate_permission_cache_drops_djangos_own_cache():
    user = agent_in(FAIRFAX)
    user.get_all_permissions()
    assert hasattr(user, "_perm_cache")
    invalidate_permission_cache(user)
    assert not hasattr(user, "_perm_cache")


@pytest.mark.django_db
def test_a_granted_role_is_live_on_the_users_next_request(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    grant_role_assignment(
        actor=company_admin(),
        target=target,
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office=office(FAIRFAX),
        business_reason="Covering the branch",
    )

    client.force_login(User.objects.get(pk=target.pk))
    shared = props(client.get(reverse("dashboard"), HTTP_X_INERTIA="true"))["user"]
    assert BRANCH_MANAGER in shared["roles"]
    assert "web.view_users" in shared["permissions"]


@pytest.mark.django_db
def test_a_future_dated_assignment_grants_nothing_yet():
    target = agent_in(FAIRFAX, email="target@example.com")
    grant_role_assignment(
        actor=company_admin(),
        target=target,
        role=BRANCH_MANAGER,
        scope_type=ScopeType.OFFICE,
        scope_office=office(FAIRFAX),
        starts_at=timezone.now() + timezone.timedelta(days=7),
        business_reason="Starts next week",
    )
    access = get_effective_access(User.objects.get(pk=target.pk))
    assert BRANCH_MANAGER not in access.role_keys


# ---------------------------------------------------------------------------
# Inactive offices
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_closed_office_stays_visible_but_cannot_be_moved_into(client):
    target = agent_in(CHARLOTTESVILLE, email="target@example.com")
    closed = office(CHARLOTTESVILLE)
    closed.is_active = False
    closed.save(update_fields=["is_active"])

    actor = company_admin()
    client.force_login(actor)
    payload = page(client, target)
    offered = {item["id"] for item in payload["options"]["offices"]}
    assert closed.pk not in offered

    # Keeping the closed office is allowed: the record must stay correctable.
    response = client.post(
        reverse("user_administration_submit", args=[target.pk]),
        admin_post(target, office=str(closed.pk), agent_status="departed"),
    )
    assert response.status_code == 302
    target.refresh_from_db()
    assert target.agent_status == "departed"

    # Moving somebody else *into* it is not.
    other = agent_in(FAIRFAX, email="other@example.com")
    response = client.post(
        reverse("user_administration_submit", args=[other.pk]),
        admin_post(other, office=str(closed.pk)),
    )
    assert response.status_code == 422
    other.refresh_from_db()
    assert other.office == office(FAIRFAX)


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_concurrent_edit_is_refused_rather_than_overwritten(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    actor = company_admin()
    client.force_login(actor)
    stale = admin_post(target, agent_status="on_leave")

    # Somebody else saves first.
    update_administration(
        actor=actor,
        target=target,
        cleaned={"agent_status": "suspended"},
        expected_version="",
    )

    response = client.post(
        reverse("user_administration_submit", args=[target.pk]), stale
    )
    assert response.status_code == 409
    target.refresh_from_db()
    assert target.agent_status == "suspended"
    assert b"Reload the page" in response.content


@pytest.mark.django_db
def test_the_version_token_moves_with_every_save(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(company_admin())
    before = page(client, target)["version"]
    assert before == ""
    client.post(
        reverse("user_administration_submit", args=[target.pk]),
        admin_post(target, agent_status="on_leave"),
    )
    after = page(client, User.objects.get(pk=target.pk))["version"]
    assert after != before


# ---------------------------------------------------------------------------
# Role assignment guards
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_working_agent_cannot_be_left_with_no_role():
    target = agent_in(FAIRFAX, email="target@example.com")
    assignment = UserRoleAssignment.objects.get(user=target, role=AGENT)
    with pytest.raises(ValidationError, match="only live role assignment"):
        revoke_role_assignment_for_user(
            actor=company_admin(),
            target=target,
            assignment=assignment,
            business_reason="Cleanup",
        )
    assignment.refresh_from_db()
    assert assignment.status == UserRoleAssignment.Status.ACTIVE


@pytest.mark.django_db
def test_a_departed_agent_may_have_their_last_role_removed():
    target = agent_in(FAIRFAX, email="target@example.com")
    target.agent_status = "departed"
    target.save(update_fields=["agent_status"])
    assignment = UserRoleAssignment.objects.get(user=target, role=AGENT)

    revoked = revoke_role_assignment_for_user(
        actor=company_admin(),
        target=target,
        assignment=assignment,
        business_reason="Left the brokerage",
    )
    assert revoked.status == UserRoleAssignment.Status.REVOKED


@pytest.mark.django_db
def test_an_assignment_belonging_to_someone_else_cannot_be_revoked(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    other = agent_in(CHARLOTTESVILLE, email="other@example.com")
    theirs = UserRoleAssignment.objects.get(user=other, role=AGENT)

    client.force_login(company_admin())
    response = client.post(
        reverse("user_administration_roles", args=[target.pk]),
        {
            "action": "revoke",
            "assignment": str(theirs.pk),
            "business_reason": "Wrong record",
        },
    )
    assert response.status_code == 404
    theirs.refresh_from_db()
    assert theirs.status == UserRoleAssignment.Status.ACTIVE


@pytest.mark.django_db
def test_a_dated_grant_records_its_effective_window(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(company_admin())
    response = client.post(
        reverse("user_administration_roles", args=[target.pk]),
        {
            "action": "grant",
            "role": BRANCH_MANAGER,
            "scope_type": ScopeType.OFFICE,
            "scope_office": str(office(FAIRFAX).pk),
            "starts_at": "2027-01-01T09:00",
            "ends_at": "2027-06-30T17:00",
            "business_reason": "Maternity cover",
        },
    )
    assert response.status_code == 302
    assignment = UserRoleAssignment.objects.get(user=target, role=BRANCH_MANAGER)
    assert assignment.status == UserRoleAssignment.Status.SCHEDULED
    assert assignment.starts_at is not None and assignment.ends_at is not None


# ---------------------------------------------------------------------------
# Contract status is owned elsewhere
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_contract_status_is_derived_and_cannot_be_typed_in(client):
    target = agent_in(FAIRFAX, email="target@example.com")
    client.force_login(company_admin())
    response = client.post(
        reverse("user_administration_submit", args=[target.pk]),
        admin_post(target, contract_status="signed", contractStatus="signed"),
    )
    assert response.status_code == 302
    target.refresh_from_db()
    assert not hasattr(target, "contract_status")
    payload = page(client, User.objects.get(pk=target.pk))
    assert payload["contractStatus"]["available"] is False
    assert payload["contractStatus"]["source"] == "contract"


# ---------------------------------------------------------------------------
# The scoped picker
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_index_lists_only_users_in_scope(client):
    agent_in(FAIRFAX, email="inscope@example.com")
    agent_in(CONNECTICUT, email="outofscope@example.com")
    client.force_login(branch_manager(FAIRFAX))
    listing = props(
        client.get(reverse("user_administration_index"), HTTP_X_INERTIA="true")
    )["users"]
    emails = {row["email"] for row in listing["items"]}
    assert "inscope@example.com" in emails
    assert "outofscope@example.com" not in emails


@pytest.mark.django_db
def test_the_index_search_cannot_widen_scope(client):
    agent_in(CONNECTICUT, email="outofscope@example.com")
    client.force_login(branch_manager(FAIRFAX))
    listing = props(
        client.get(
            reverse("user_administration_index"),
            {"q": "outofscope"},
            HTTP_X_INERTIA="true",
        )
    )["users"]
    assert listing["items"] == []


@pytest.mark.django_db
def test_an_agent_cannot_open_the_index(client):
    client.force_login(agent_in(FAIRFAX))
    response = client.get(reverse("user_administration_index"))
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Onboarding still works with the new default status
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_new_user_starts_active_and_unverified(client):
    user = User.objects.create_user(email="new@example.com")
    client.force_login(user)
    response = client.post(reverse("onboarding_submit"), valid_profile_post())
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.agent_status == "active"
    assert user.license_verification_state == "unverified"
    assert user.administration_updated_at is None
