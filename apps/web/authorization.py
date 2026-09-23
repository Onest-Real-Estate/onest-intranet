from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from functools import wraps
from typing import Any, Literal, cast

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.services.role_assignments import get_effective_access
from apps.web.capability import matches_permission_check
from apps.web.operations import OPERATIONS_DESTINATIONS, operations_policy_key

logger = logging.getLogger("apps.authorization")

AccessLevel = Literal[
    "public",
    "authenticated",
    "onboarding_only",
    "permission_protected",
]
AuthBehavior = Literal["redirect", "json"]


@dataclass(frozen=True)
class AuthorizationPolicy:
    key: str
    access: AccessLevel
    description: str
    methods: tuple[str, ...]
    route_names: tuple[str, ...] = ()
    path_prefixes: tuple[str, ...] = ()
    any_permissions: tuple[str, ...] = ()
    all_permissions: tuple[str, ...] = ()
    scope_rule: str = "none"
    allow_incomplete_profile: bool = False
    auth_behavior: AuthBehavior = "redirect"
    denial_status: int = 403
    surface_type: str = "route"


ROUTE_POLICIES: dict[str, AuthorizationPolicy] = {
    "login_page": AuthorizationPolicy(
        key="login_page",
        access="public",
        description="Microsoft SSO landing page.",
        methods=("GET",),
        route_names=("login",),
    ),
    "login_redirect_alias": AuthorizationPolicy(
        key="login_redirect_alias",
        access="public",
        description="Legacy /login alias that redirects to /.",
        methods=("GET",),
        path_prefixes=("/login",),
    ),
    "logout": AuthorizationPolicy(
        key="logout",
        access="authenticated",
        description="End the current session safely.",
        methods=("POST",),
        route_names=("logout",),
        allow_incomplete_profile=True,
    ),
    "onboarding": AuthorizationPolicy(
        key="onboarding",
        access="onboarding_only",
        description="Collect required post-SSO profile details.",
        methods=("GET",),
        route_names=("onboarding",),
        allow_incomplete_profile=True,
        scope_rule="self_only",
    ),
    "onboarding_stream_token": AuthorizationPolicy(
        key="onboarding_stream_token",
        access="authenticated",
        description="Issue short-lived, self-only onboarding stream credentials.",
        methods=("GET",),
        route_names=("onboarding_stream_token",),
        allow_incomplete_profile=True,
        scope_rule="self_only",
        auth_behavior="json",
    ),
    "onboarding_profile_save": AuthorizationPolicy(
        key="onboarding_profile_save",
        access="onboarding_only",
        description=(
            "Save one onboarding profile section for the signed-in user without "
            "completing the profile."
        ),
        methods=("POST",),
        route_names=("onboarding_profile_save",),
        allow_incomplete_profile=True,
        scope_rule="self_only",
    ),
    "onboarding_office_preview": AuthorizationPolicy(
        key="onboarding_office_preview",
        access="onboarding_only",
        description=(
            "Return the public confirmation card and current resolved Branch Admin "
            "for one active, assignable office."
        ),
        methods=("GET",),
        route_names=("onboarding_office_preview",),
        allow_incomplete_profile=True,
        scope_rule="self_only",
        auth_behavior="json",
    ),
    "onboarding_profile_finalize": AuthorizationPolicy(
        key="onboarding_profile_finalize",
        access="onboarding_only",
        description=(
            "Confirm the reviewed onboarding profile and complete it atomically "
            "once every required fact and the stored headshot are present."
        ),
        methods=("POST",),
        route_names=("onboarding_profile_finalize",),
        allow_incomplete_profile=True,
        scope_rule="self_only",
    ),
    "headshot_upload": AuthorizationPolicy(
        key="headshot_upload",
        access="authenticated",
        description=(
            "Replace or remove the current user's headshot, from onboarding "
            "or the profile page."
        ),
        methods=("POST",),
        route_names=("headshot_upload",),
        allow_incomplete_profile=True,
        scope_rule="self_only",
        auth_behavior="json",
    ),
    "headshot_display": AuthorizationPolicy(
        key="headshot_display",
        access="authenticated",
        description="Stream the signed-in user's headshot for avatar display.",
        methods=("GET",),
        route_names=("headshot_display",),
        allow_incomplete_profile=True,
        scope_rule="self_only",
    ),
    "profile": AuthorizationPolicy(
        key="profile",
        access="authenticated",
        description="Render the signed-in user's own agent profile editor.",
        methods=("GET",),
        route_names=("profile",),
        scope_rule="self_only",
    ),
    "profile_submit": AuthorizationPolicy(
        key="profile_submit",
        access="authenticated",
        description=(
            "Persist the signed-in user's self-editable profile fields. "
            "Never addresses a user identifier supplied by the client."
        ),
        methods=("POST",),
        route_names=("profile_submit",),
        scope_rule="self_only",
    ),
    "user_administration": AuthorizationPolicy(
        key="user_administration",
        access="permission_protected",
        description=(
            "Render one user's broker-controlled profile record. The subject "
            "is resolved through the actor's scoped queryset, so an "
            "out-of-scope id is a 404."
        ),
        methods=("GET",),
        route_names=("user_administration",),
        all_permissions=("user.view_user_administration",),
        scope_rule="administered_user_scope",
    ),
    "user_administration_submit": AuthorizationPolicy(
        key="user_administration_submit",
        access="permission_protected",
        description=(
            "Persist broker-controlled profile fields for one user. Never "
            "accepts a role, permission, or account-status change."
        ),
        methods=("POST",),
        route_names=("user_administration_submit",),
        all_permissions=("user.change_user_administration",),
        scope_rule="administered_user_delegation_scope",
    ),
    "user_administration_roles": AuthorizationPolicy(
        key="user_administration_roles",
        access="permission_protected",
        description=(
            "Grant or revoke one role assignment for a user, through the "
            "role-assignment service and its own delegation rules."
        ),
        methods=("POST",),
        route_names=("user_administration_roles",),
        all_permissions=("user.change_user_administration",),
        scope_rule="role_delegation_scope",
    ),
    "role_assignment_workspace": AuthorizationPolicy(
        key="role_assignment_workspace",
        access="permission_protected",
        description=(
            "Render one user's role-assignment workspace inside the actor's "
            "delegation scope."
        ),
        methods=("GET",),
        route_names=("admin_assign_roles_user",),
        all_permissions=("web.assign_user_roles",),
        scope_rule="role_delegation_scope",
    ),
    "role_assignment_preview": AuthorizationPolicy(
        key="role_assignment_preview",
        access="permission_protected",
        description=(
            "Dry-run the effective access change for a grant, edit, or revoke "
            "before confirmation."
        ),
        methods=("POST",),
        route_names=("admin_assign_roles_preview",),
        all_permissions=("web.assign_user_roles",),
        scope_rule="role_delegation_scope",
    ),
    "role_assignment_mutate": AuthorizationPolicy(
        key="role_assignment_mutate",
        access="permission_protected",
        description=(
            "Grant, edit, or revoke a role assignment through the dedicated "
            "assignment administration surface."
        ),
        methods=("POST",),
        route_names=("admin_assign_roles_mutate",),
        all_permissions=("web.assign_user_roles",),
        scope_rule="role_delegation_scope",
    ),
    "user_account_state": AuthorizationPolicy(
        key="user_account_state",
        access="permission_protected",
        description=(
            "Disable or reactivate one account in scope. Carries its own "
            "permission: maintaining somebody's record is not the same grant "
            "as ending their sessions."
        ),
        methods=("POST",),
        route_names=("user_account_state",),
        all_permissions=(
            "user.view_user_administration",
            "user.manage_account_state",
        ),
        scope_rule="administered_user_delegation_scope",
    ),
    "office_administration_detail": AuthorizationPolicy(
        key="office_administration_detail",
        access="permission_protected",
        description="Render one office record inside the actor's office-tree scope.",
        methods=("GET",),
        route_names=("admin_office",),
        all_permissions=("web.manage_offices",),
        scope_rule="office_tree_scope",
    ),
    "office_administration_update": AuthorizationPolicy(
        key="office_administration_update",
        access="permission_protected",
        description="Update operational office information within scope.",
        methods=("POST",),
        route_names=("admin_office_update",),
        all_permissions=("web.manage_offices",),
        scope_rule="office_tree_scope",
    ),
    "office_administration_structure": AuthorizationPolicy(
        key="office_administration_structure",
        access="permission_protected",
        description=(
            "Apply high-impact hierarchy or status changes after impact "
            "confirmation. Company-wide authority is re-checked in the service."
        ),
        methods=("POST",),
        route_names=("admin_office_structure",),
        all_permissions=("web.manage_offices",),
        scope_rule="office_tree_scope",
    ),
    "office_administration_impact": AuthorizationPolicy(
        key="office_administration_impact",
        access="permission_protected",
        description="Dry-run impact analysis for hierarchy or status changes.",
        methods=("POST",),
        route_names=("admin_office_impact",),
        all_permissions=("web.manage_offices",),
        scope_rule="office_tree_scope",
    ),
    "office_administration_contact": AuthorizationPolicy(
        key="office_administration_contact",
        access="permission_protected",
        description="Create or update an office contact assignment.",
        methods=("POST",),
        route_names=("admin_office_contact",),
        all_permissions=("web.manage_offices",),
        scope_rule="office_tree_scope",
    ),
    "office_administration_contact_end": AuthorizationPolicy(
        key="office_administration_contact_end",
        access="permission_protected",
        description="End an office contact assignment.",
        methods=("POST",),
        route_names=("admin_office_contact_end",),
        all_permissions=("web.manage_offices",),
        scope_rule="office_tree_scope",
    ),
    "admin_office_resources": AuthorizationPolicy(
        key="admin_office_resources",
        access="permission_protected",
        description=(
            "Scoped office resources console: list and filter the catalog "
            "within the actor's office-tree grant."
        ),
        methods=("GET",),
        route_names=("admin_office_resources",),
        all_permissions=("web.view_office_resources_admin",),
        scope_rule="office_tree_scope",
    ),
    "admin_office_resource_new": AuthorizationPolicy(
        key="admin_office_resource_new",
        access="permission_protected",
        description="Render the create form for a scoped office resource.",
        methods=("GET",),
        route_names=("admin_office_resource_new",),
        all_permissions=("web.manage_office_resources",),
        scope_rule="office_tree_scope",
    ),
    "admin_office_resource_create": AuthorizationPolicy(
        key="admin_office_resource_create",
        access="permission_protected",
        description="Create an office resource within the actor's boundary.",
        methods=("POST",),
        route_names=("admin_office_resource_create",),
        all_permissions=("web.manage_office_resources",),
        scope_rule="office_tree_scope",
    ),
    "admin_office_resource": AuthorizationPolicy(
        key="admin_office_resource",
        access="permission_protected",
        description=(
            "Render one scoped office resource workspace with optional "
            "in-scope library preview."
        ),
        methods=("GET",),
        route_names=("admin_office_resource",),
        all_permissions=("web.view_office_resources_admin",),
        scope_rule="office_tree_scope",
    ),
    "admin_office_resource_update": AuthorizationPolicy(
        key="admin_office_resource_update",
        access="permission_protected",
        description=("Edit one scoped office resource with optimistic concurrency."),
        methods=("POST",),
        route_names=("admin_office_resource_update",),
        all_permissions=("web.manage_office_resources",),
        scope_rule="office_tree_scope",
    ),
    "admin_office_resource_file": AuthorizationPolicy(
        key="admin_office_resource_file",
        access="permission_protected",
        description="Upload or replace one scoped resource file.",
        methods=("POST",),
        route_names=("admin_office_resource_file",),
        all_permissions=("web.manage_office_resources",),
        scope_rule="office_tree_scope",
    ),
    "admin_office_resource_transition": AuthorizationPolicy(
        key="admin_office_resource_transition",
        access="permission_protected",
        description=(
            "Lifecycle transitions (activate, deactivate, archive, reorder) "
            "for one scoped office resource."
        ),
        methods=("POST",),
        route_names=("admin_office_resource_transition",),
        all_permissions=("web.manage_office_resources",),
        scope_rule="office_tree_scope",
    ),
    "admin_inventory_create": AuthorizationPolicy(
        key="admin_inventory_create",
        access="permission_protected",
        description="Create an inventory item within the actor's boundary.",
        methods=("POST",),
        route_names=("admin_inventory_create",),
        all_permissions=("inventory.manage_inventory",),
        scope_rule="inventory_office_scope",
    ),
    "admin_inventory_item": AuthorizationPolicy(
        key="admin_inventory_item",
        access="permission_protected",
        description="Render one scoped inventory item workspace.",
        methods=("GET",),
        route_names=("admin_inventory_item",),
        all_permissions=("web.view_inventory",),
        scope_rule="inventory_office_scope",
    ),
    "admin_inventory_update": AuthorizationPolicy(
        key="admin_inventory_update",
        access="permission_protected",
        description="Edit one scoped inventory item with optimistic concurrency.",
        methods=("POST",),
        route_names=("admin_inventory_update",),
        all_permissions=("inventory.manage_inventory",),
        scope_rule="inventory_office_scope",
    ),
    "admin_inventory_transition": AuthorizationPolicy(
        key="admin_inventory_transition",
        access="permission_protected",
        description=(
            "Lifecycle transitions (unavailable, damaged, lost, restore, retire) "
            "for one scoped inventory item."
        ),
        methods=("POST",),
        route_names=("admin_inventory_transition",),
        all_permissions=("inventory.manage_inventory",),
        scope_rule="inventory_office_scope",
    ),
    "admin_inventory_transfer": AuthorizationPolicy(
        key="admin_inventory_transfer",
        access="permission_protected",
        description="Transfer one scoped inventory item between offices.",
        methods=("POST",),
        route_names=("admin_inventory_transfer",),
        all_permissions=("inventory.manage_inventory",),
        scope_rule="inventory_office_scope",
    ),
    "admin_inventory_photo": AuthorizationPolicy(
        key="admin_inventory_photo",
        access="permission_protected",
        description="Upload or replace one scoped inventory photo.",
        methods=("POST",),
        route_names=("admin_inventory_photo",),
        all_permissions=("inventory.manage_inventory",),
        scope_rule="inventory_office_scope",
    ),
    "office_info": AuthorizationPolicy(
        key="office_info",
        access="authenticated",
        description=(
            "Agent-facing office brochure for the signed-in user's primary "
            "office. Never accepts an office id from the client."
        ),
        methods=("GET",),
        route_names=("office_info",),
        scope_rule="self_only",
    ),
    "office_resources": AuthorizationPolicy(
        key="office_resources",
        access="authenticated",
        description=(
            "Effective office resources for the signed-in user's primary "
            "office. Scope chain resolved server-side; never accepts an "
            "office or resource identifier from the client."
        ),
        methods=("GET",),
        route_names=("office_resources",),
        scope_rule="self_only",
    ),
    "onboarding_tool_catalog": AuthorizationPolicy(
        key="onboarding_tool_catalog",
        access="permission_protected",
        description=(
            "Add, edit, reorder, and retire the agent tool catalog, including "
            "which offices each tool applies to and the guide agents follow. "
            "Brokerage-wide configuration, so it is a separate grant from "
            "moving one agent's checklist — a branch manager runs onboarding "
            "for their branch without redefining what every office needs."
        ),
        methods=("GET", "POST"),
        route_names=(
            "onboarding_tool_catalog",
            "onboarding_tool_create",
            "onboarding_tool_save",
            "onboarding_tool_reorder",
        ),
        all_permissions=("web.manage_onboarding_tools",),
        scope_rule="brokerage_wide",
    ),
    "my_tools": AuthorizationPolicy(
        key="my_tools",
        access="authenticated",
        description=(
            "The signed-in agent's own tool checklist and setup guides. No "
            "grant: a person is always entitled to know what they are expected "
            "to have and how to obtain it. Reads only their own row set, and "
            'writes only their own "I have this" mark, never the '
            "staff-confirmed state."
        ),
        methods=("GET", "POST"),
        route_names=("my_tools", "my_tool_have"),
        scope_rule="self_only",
    ),
    "operations_people": AuthorizationPolicy(
        key="operations_people",
        access="permission_protected",
        description=(
            "The single People entry in the navigation. Redirects to the first "
            "tab this reader may open — Users, Roles & permissions, or New "
            "agents — each of which enforces its own policy on arrival."
        ),
        methods=("GET",),
        route_names=("admin_people",),
        any_permissions=(
            "web.view_users",
            "web.assign_user_roles",
            "web.view_new_agents",
        ),
    ),
    "team_tool_readiness": AuthorizationPolicy(
        key="team_tool_readiness",
        access="permission_protected",
        description=(
            "Tool readiness for the people this reader covers, and the write "
            "that moves one row. Scoped by the office tree in SQL before "
            "counting; an agent outside that reach is a 404. The write "
            "additionally requires the onboarding grant and refuses "
            "self-management."
        ),
        methods=("GET", "POST"),
        route_names=("team_tool_readiness", "agent_tools", "agent_tool_state"),
        all_permissions=("web.view_new_agents",),
        scope_rule="office_tree_scope",
    ),
    "it_support_submit": AuthorizationPolicy(
        key="it_support_submit",
        access="authenticated",
        description=(
            "The IT request form and the requester's own ticket list. Open to "
            "every authenticated person on purpose: gating it would mean the "
            "people most likely to hit an account or access bug are the ones "
            "who cannot report it. The list is filtered to tickets the reader "
            "raised or is the subject of."
        ),
        methods=("GET", "POST"),
        route_names=("it_support", "it_support_create"),
        scope_rule="self_only",
    ),
    "it_support_detail": AuthorizationPolicy(
        key="it_support_detail",
        access="authenticated",
        description=(
            "One ticket by public id. Loaded through the reader's own scoped "
            "queryset, so a ticket they neither raised nor may triage is a 404 "
            "rather than a 403. Internal notes and diagnostics are excluded "
            "from the payload for a reader without the note grant."
        ),
        methods=("GET",),
        route_names=("it_support_ticket",),
        scope_rule="support_request_scope",
    ),
    "it_support_write": AuthorizationPolicy(
        key="it_support_write",
        access="authenticated",
        description=(
            "Reply, attach, transition, assign, and prioritise. Authenticated "
            "at the route because a requester may reply on and attach to their "
            "own ticket; each write then re-checks its own specific grant in "
            "the service, where the ticket's submitter is also known."
        ),
        methods=("POST",),
        route_names=(
            "it_support_reply",
            "it_support_attach",
            "it_support_transition",
            "it_support_assign",
            "it_support_priority",
        ),
        scope_rule="support_request_scope",
    ),
    "it_support_attachment": AuthorizationPolicy(
        key="it_support_attachment",
        access="authenticated",
        description=(
            "Streams one ticket attachment from protected storage. The parent "
            "ticket is resolved inside the reader's scope and the file inside "
            "the visible-attachment queryset, so an IT-only file is a 404 "
            "rather than a 403 for a requester. No signed link, no public URL."
        ),
        methods=("GET",),
        route_names=("it_support_attachment",),
        scope_rule="support_request_scope",
    ),
    "office_inventory": AuthorizationPolicy(
        key="office_inventory",
        access="authenticated",
        description=(
            "Agent Office Inventory browser for the signed-in user's primary "
            "office. Returns only active reservable records; never accepts an "
            "office id from the client."
        ),
        methods=("GET",),
        route_names=("office_inventory",),
        scope_rule="self_only",
    ),
    "office_inventory_item": AuthorizationPolicy(
        key="office_inventory_item",
        access="authenticated",
        description=(
            "One reservable inventory item resolved through the reader's "
            "office-scoped queryset so a foreign office id is a 404."
        ),
        methods=("GET",),
        route_names=("office_inventory_item",),
        scope_rule="self_only",
    ),
    "office_inventory_photo": AuthorizationPolicy(
        key="office_inventory_photo",
        access="authenticated",
        description=(
            "Stream an agent-visible inventory photo after re-checking the "
            "reader's office catalog and photo_is_public."
        ),
        methods=("GET",),
        route_names=("office_inventory_photo",),
        scope_rule="self_only",
    ),
    "agent_directory": AuthorizationPolicy(
        key="agent_directory",
        access="authenticated",
        description=(
            "Company-wide peer Agent Directory. Visibility and field "
            "allowlisting are enforced in the service layer; inactive and "
            "non-engaged people never appear in search, counts, or filters."
        ),
        methods=("GET",),
        route_names=("agent_directory",),
        scope_rule="self_only",
    ),
    "agent_directory_detail": AuthorizationPolicy(
        key="agent_directory_detail",
        access="authenticated",
        description=(
            "One directory-visible person. Out-of-policy ids are 404 so "
            "direct URLs cannot confirm hidden accounts."
        ),
        methods=("GET",),
        route_names=("agent_directory_detail",),
        scope_rule="self_only",
    ),
    "agent_directory_headshot": AuthorizationPolicy(
        key="agent_directory_headshot",
        access="authenticated",
        description=(
            "Stream a directory-visible headshot after re-checking "
            "visibility. Never returns a permanent public media URL."
        ),
        methods=("GET",),
        route_names=("agent_directory_headshot",),
        scope_rule="self_only",
    ),
    "room_availability": AuthorizationPolicy(
        key="room_availability",
        access="permission_protected",
        description=(
            "Bounded room-availability calendar. The default office comes from "
            "the signed-in user; any alternate office is re-checked against "
            "effective organizational scope before serialization."
        ),
        methods=("GET",),
        route_names=("room_availability",),
        all_permissions=("reservations.book_spaces",),
        scope_rule="reservation_office_scope",
    ),
    "room_reservation_new": AuthorizationPolicy(
        key="room_reservation_new",
        access="permission_protected",
        description="Review one scoped room slot before authoritative submission.",
        methods=("GET",),
        route_names=("room_reservation_new",),
        all_permissions=("reservations.book_spaces",),
        scope_rule="reservation_office_scope",
    ),
    "room_reservation_create": AuthorizationPolicy(
        key="room_reservation_create",
        access="permission_protected",
        description=(
            "Create one room reservation after rule, schedule, scope, and "
            "race-proof overlap validation."
        ),
        methods=("POST",),
        route_names=("room_reservation_create",),
        all_permissions=("reservations.book_spaces",),
        scope_rule="reservation_office_scope",
    ),
    "inventory_reservations_mine": AuthorizationPolicy(
        key="inventory_reservations_mine",
        access="authenticated",
        description=(
            "Self-service list of the signed-in user's inventory reservations. "
            "Never accepts a user selector."
        ),
        methods=("GET",),
        route_names=("inventory_reservations_mine",),
        scope_rule="self_only",
    ),
    "inventory_reservation_new": AuthorizationPolicy(
        key="inventory_reservation_new",
        access="authenticated",
        description=(
            "Agent reservation form and authoritative availability/terms "
            "summary for the reader's office inventory."
        ),
        methods=("GET",),
        route_names=("inventory_reservation_new",),
        scope_rule="self_only",
    ),
    "inventory_reservation_create": AuthorizationPolicy(
        key="inventory_reservation_create",
        access="authenticated",
        description=(
            "Create an inventory reservation for the signed-in user after "
            "revalidating availability under the item lock."
        ),
        methods=("POST",),
        route_names=("inventory_reservation_create",),
        scope_rule="self_only",
    ),
    "inventory_reservation_detail": AuthorizationPolicy(
        key="inventory_reservation_detail",
        access="authenticated",
        description=(
            "Confirmation and detail for one of the signed-in user's "
            "inventory reservations."
        ),
        methods=("GET",),
        route_names=("inventory_reservation_detail",),
        scope_rule="self_only",
    ),
    "inventory_reservation_cancel": AuthorizationPolicy(
        key="inventory_reservation_cancel",
        access="authenticated",
        description=("Cancel an owned inventory reservation before the policy cutoff."),
        methods=("POST",),
        route_names=("inventory_reservation_cancel",),
        scope_rule="self_only",
    ),
    "admin_reservation_detail": AuthorizationPolicy(
        key="admin_reservation_detail",
        access="permission_protected",
        description="Render one scoped inventory reservation workspace.",
        methods=("GET",),
        route_names=("admin_reservation_detail",),
        all_permissions=("web.view_reservations",),
        scope_rule="reservation_office_scope",
    ),
    "admin_reservation_transition": AuthorizationPolicy(
        key="admin_reservation_transition",
        access="permission_protected",
        description=(
            "Lifecycle transitions (approve, checkout, return, exceptions) "
            "for one scoped inventory reservation."
        ),
        methods=("POST",),
        route_names=("admin_reservation_transition",),
        any_permissions=(
            "inventory.approve_reservations",
            "inventory.override_reservations",
        ),
        scope_rule="reservation_office_scope",
    ),
    "feedback_submit": AuthorizationPolicy(
        key="feedback_submit",
        access="authenticated",
        description=(
            "The support form. Open to every authenticated person on purpose: "
            "gating it would mean the people most likely to hit a permission "
            "bug are the ones who cannot report it."
        ),
        methods=("GET",),
        route_names=("feedback_submit",),
        scope_rule="self_only",
    ),
    "feedback_mine": AuthorizationPolicy(
        key="feedback_mine",
        access="authenticated",
        description=(
            "The submitter's own tickets. `for_reader` with `can_triage=False` "
            "returns their rows and nobody else's, whatever office they are in."
        ),
        methods=("GET",),
        route_names=("feedback_mine",),
        scope_rule="self_only",
    ),
    "feedback_detail": AuthorizationPolicy(
        key="feedback_detail",
        access="authenticated",
        description=(
            "One ticket, loaded through the reader's own scoped queryset so an "
            "id outside their reach is a 404 rather than a 403. Triage "
            "capability widens which tickets resolve, never what the route "
            "allows."
        ),
        methods=("GET",),
        route_names=("feedback_detail",),
        scope_rule="feedback_reader_scope",
    ),
    "feedback_screenshot": AuthorizationPolicy(
        key="feedback_screenshot",
        access="authenticated",
        description=(
            "One attached image, authorized at access time and streamed. The "
            "parent ticket is loaded through the reader's scoped queryset "
            "first, so nothing durable is handed out that could outlive their "
            "access."
        ),
        methods=("GET",),
        route_names=("feedback_screenshot",),
        scope_rule="feedback_reader_scope",
    ),
    "feedback_write": AuthorizationPolicy(
        key="feedback_write",
        access="authenticated",
        description=(
            "Submit a report, or reply on a ticket. The service decides what "
            "each actor may write — a submitter replies on their own ticket, "
            "an internal note needs the note grant."
        ),
        methods=("POST",),
        route_names=("feedback_create", "feedback_note"),
        scope_rule="feedback_reader_scope",
    ),
    "feedback_triage_write": AuthorizationPolicy(
        key="feedback_triage_write",
        access="permission_protected",
        description=(
            "Transition, assign, prioritise, and convert. Each write re-checks "
            "its own specific grant in the service."
        ),
        methods=("POST",),
        route_names=(
            "feedback_transition",
            "feedback_assign",
            "feedback_prioritise",
            "feedback_convert",
        ),
        all_permissions=("web.triage_feedback",),
        scope_rule="feedback_office_scope",
    ),
    "operational_task_detail": AuthorizationPolicy(
        key="operational_task_detail",
        access="permission_protected",
        description=(
            "One task by public id, loaded through the reader's own scoped "
            "queryset so an id outside their reach is a 404 rather than a 403."
        ),
        methods=("GET",),
        route_names=("operational_task_detail",),
        all_permissions=("web.view_operational_tasks",),
        scope_rule="operational_task_reader_scope",
    ),
    "operational_task_write": AuthorizationPolicy(
        key="operational_task_write",
        access="permission_protected",
        description=(
            "Create, transition, assign, and comment. The route gate is the "
            "read grant on purpose — each write re-checks its own specific "
            "grant in the service, where the task's assignee is also known."
        ),
        methods=("POST",),
        route_names=(
            "operational_task_create",
            "operational_task_transition",
            "operational_task_assign",
            "operational_task_comment",
            "operational_task_attach",
        ),
        all_permissions=("web.view_operational_tasks",),
        scope_rule="operational_task_reader_scope",
    ),
    "operational_task_attachment": AuthorizationPolicy(
        key="operational_task_attachment",
        access="permission_protected",
        description=(
            "Streams one task attachment from protected storage. The parent "
            "task is resolved inside the reader's scope and the file inside "
            "the visible-attachment queryset, so an internal file is a 404 "
            "rather than a 403 for a reader without the management grant. "
            "There is no signed link and no public URL."
        ),
        methods=("GET",),
        route_names=("operational_task_attachment",),
        all_permissions=("web.view_operational_tasks",),
        scope_rule="operational_task_reader_scope",
    ),
    "announcements_feed": AuthorizationPolicy(
        key="announcements_feed",
        access="authenticated",
        description=(
            "Announcement feed for the signed-in user. Audience is the "
            "reader's own office scope chain, resolved server-side; category "
            "and priority arrive as validated codes and can only narrow the "
            "set, never widen it."
        ),
        methods=("GET",),
        route_names=("announcements",),
        scope_rule="announcement_audience_scope",
    ),
    "announcement_detail": AuthorizationPolicy(
        key="announcement_detail",
        access="authenticated",
        description=(
            "One announcement by id. Authorized by the same audience "
            "predicate as the feed, so a guessed id is no more permissive "
            "than the list the reader was shown."
        ),
        methods=("GET",),
        route_names=("announcement_detail",),
        scope_rule="announcement_audience_scope",
    ),
    "announcement_media": AuthorizationPolicy(
        key="announcement_media",
        access="authenticated",
        description=(
            "Stream one announcement file from protected storage. Audience is "
            "re-evaluated on every request and the file must have passed "
            "processing; no presigned or otherwise durable URL is issued."
        ),
        methods=("GET",),
        route_names=("announcement_media",),
        scope_rule="announcement_audience_scope",
    ),
    "announcement_media_variant": AuthorizationPolicy(
        key="announcement_media_variant",
        access="authenticated",
        description=(
            "Stream one generated derivative behind exactly the same audience "
            "check as its original."
        ),
        methods=("GET",),
        route_names=("announcement_media_variant",),
        scope_rule="announcement_audience_scope",
    ),
    "announcement_media_manager": AuthorizationPolicy(
        key="announcement_media_manager",
        access="permission_protected",
        description=(
            "Manage one announcement's hero image and attachments. Scoped to "
            "the actor's publishing offices; shows quarantine state, which "
            "recipients never see."
        ),
        methods=("GET",),
        route_names=("announcement_media_manager",),
        all_permissions=("web.manage_announcements",),
        scope_rule="office_tree_scope",
    ),
    "announcement_media_upload": AuthorizationPolicy(
        key="announcement_media_upload",
        access="permission_protected",
        description="Upload a hero image or attachment to a scoped announcement.",
        methods=("POST",),
        route_names=("announcement_media_upload",),
        all_permissions=("web.manage_announcements",),
        scope_rule="office_tree_scope",
        auth_behavior="json",
    ),
    "announcement_media_replace": AuthorizationPolicy(
        key="announcement_media_replace",
        access="permission_protected",
        description="Replace one stored announcement file in place.",
        methods=("POST",),
        route_names=("announcement_media_replace",),
        all_permissions=("web.manage_announcements",),
        scope_rule="office_tree_scope",
        auth_behavior="json",
    ),
    "announcement_media_remove": AuthorizationPolicy(
        key="announcement_media_remove",
        access="permission_protected",
        description=(
            "Remove one announcement file. Deleted while the announcement is a "
            "draft; retained but deactivated once it has been published."
        ),
        methods=("POST",),
        route_names=("announcement_media_remove",),
        all_permissions=("web.manage_announcements",),
        scope_rule="office_tree_scope",
    ),
    "announcement_media_reorder": AuthorizationPolicy(
        key="announcement_media_reorder",
        access="permission_protected",
        description="Set the display order of one announcement's attachments.",
        methods=("POST",),
        route_names=("announcement_media_reorder",),
        all_permissions=("web.manage_announcements",),
        scope_rule="office_tree_scope",
    ),
    "announcement_new": AuthorizationPolicy(
        key="announcement_new",
        access="permission_protected",
        description=(
            "Open an empty announcement workspace. Every choice the form "
            "offers — owning office, region, office, role, person — is built "
            "from the actor's own grant."
        ),
        methods=("GET",),
        route_names=("announcement_new",),
        all_permissions=("web.manage_announcements",),
        scope_rule="publication_scope",
    ),
    "announcement_edit": AuthorizationPolicy(
        key="announcement_edit",
        access="permission_protected",
        description=(
            "Open one announcement in the workspace. Loaded through the "
            "actor's scoped queryset, so an out-of-scope id is a 404 and not a "
            "confirmation that the record exists."
        ),
        methods=("GET",),
        route_names=("announcement_edit",),
        all_permissions=("web.manage_announcements",),
        scope_rule="publication_scope",
    ),
    "announcement_create": AuthorizationPolicy(
        key="announcement_create",
        access="permission_protected",
        description=(
            "Create one announcement draft. A draft reaches nobody; "
            "publication is a separate action behind a separate grant."
        ),
        methods=("POST",),
        route_names=("announcement_create",),
        all_permissions=("web.manage_announcements",),
        scope_rule="publication_scope",
    ),
    "announcement_update": AuthorizationPolicy(
        key="announcement_update",
        access="permission_protected",
        description=(
            "Save one announcement's copy, window, call to action, and "
            "audience. Guarded by an update-timestamp token, so a concurrent "
            "edit is a 409 rather than a lost update."
        ),
        methods=("POST",),
        route_names=("announcement_update",),
        all_permissions=("web.manage_announcements",),
        scope_rule="publication_scope",
    ),
    "announcement_lifecycle": AuthorizationPolicy(
        key="announcement_lifecycle",
        access="permission_protected",
        description=(
            "Publish, schedule, unpublish, archive, or restore one "
            "announcement. Needs the publication grant on top of authoring, "
            "and re-authorizes every stored audience selector before the "
            "state changes."
        ),
        methods=("POST",),
        route_names=("announcement_lifecycle",),
        all_permissions=(
            "web.manage_announcements",
            "web.publish_announcements",
        ),
        scope_rule="publication_scope",
    ),
    "announcement_pin": AuthorizationPolicy(
        key="announcement_pin",
        access="permission_protected",
        description=(
            "Pin or unpin one published announcement. Ordering only — pinning "
            "never changes who can read it."
        ),
        methods=("POST",),
        route_names=("announcement_pin",),
        all_permissions=("web.manage_announcements", "web.pin_announcements"),
        scope_rule="publication_scope",
    ),
    "announcement_recipient_search": AuthorizationPolicy(
        key="announcement_recipient_search",
        access="permission_protected",
        description=(
            "Typeahead for individual announcement recipients, bounded by the "
            "actor's administered users. Answers JSON and returns nothing "
            "below the minimum query length, so it cannot be used to "
            "enumerate the directory."
        ),
        methods=("GET",),
        route_names=("announcement_recipient_search",),
        all_permissions=("web.manage_announcements",),
        scope_rule="delegated_user_scope",
        auth_behavior="json",
    ),
    "announcement_article_fetch": AuthorizationPolicy(
        key="announcement_article_fetch",
        access="permission_protected",
        description=(
            "Fetch Open Graph and page metadata for a pasted public article "
            "URL. SSRF-hardened; returns reviewable suggestions only."
        ),
        methods=("POST",),
        route_names=("announcement_article_fetch",),
        all_permissions=("web.manage_announcements",),
        scope_rule="publication_scope",
        auth_behavior="json",
    ),
    "announcement_article_summarize": AuthorizationPolicy(
        key="announcement_article_summarize",
        access="permission_protected",
        description=(
            "Opt-in AI teaser and digest from a prior article fetch extract. "
            "Never runs on save or publish."
        ),
        methods=("POST",),
        route_names=("announcement_article_summarize",),
        all_permissions=("web.manage_announcements",),
        scope_rule="publication_scope",
        auth_behavior="json",
    ),
    "announcement_article_import_hero": AuthorizationPolicy(
        key="announcement_article_import_hero",
        access="permission_protected",
        description=(
            "Import a remote article image candidate through the validated "
            "hero media pipeline for a scoped announcement."
        ),
        methods=("POST",),
        route_names=("announcement_article_import_hero",),
        all_permissions=("web.manage_announcements",),
        scope_rule="publication_scope",
        auth_behavior="json",
    ),
    "training_library": AuthorizationPolicy(
        key="training_library",
        access="authenticated",
        description=(
            "Training library for the signed-in user. Audience is resolved "
            "server-side; filters can only narrow the visible set."
        ),
        methods=("GET",),
        route_names=("training_learning",),
        scope_rule="training_audience_scope",
    ),
    "training_detail": AuthorizationPolicy(
        key="training_detail",
        access="authenticated",
        description=(
            "One training item by id. Authorized by the same audience "
            "predicate as the library."
        ),
        methods=("GET",),
        route_names=("training_detail",),
        scope_rule="training_audience_scope",
    ),
    "training_media": AuthorizationPolicy(
        key="training_media",
        access="authenticated",
        description=(
            "Stream one training file from protected storage. Audience is "
            "re-checked on every request."
        ),
        methods=("GET",),
        route_names=("training_media",),
        scope_rule="training_audience_scope",
    ),
    "training_new": AuthorizationPolicy(
        key="training_new",
        access="permission_protected",
        description="Open an empty training workspace within the actor's grant.",
        methods=("GET",),
        route_names=("training_new",),
        all_permissions=("web.manage_training",),
        scope_rule="publication_scope",
    ),
    "training_edit": AuthorizationPolicy(
        key="training_edit",
        access="permission_protected",
        description=(
            "Open one training item in the workspace. Loaded through the "
            "actor's scoped queryset, so an out-of-scope id is a 404."
        ),
        methods=("GET",),
        route_names=("training_edit",),
        all_permissions=("web.manage_training",),
        scope_rule="publication_scope",
    ),
    "training_create": AuthorizationPolicy(
        key="training_create",
        access="permission_protected",
        description="Create one training draft. Publication is a separate action.",
        methods=("POST",),
        route_names=("training_create",),
        all_permissions=("web.manage_training",),
        scope_rule="publication_scope",
    ),
    "training_update": AuthorizationPolicy(
        key="training_update",
        access="permission_protected",
        description=(
            "Save training copy, window, required state, and audience. Guarded "
            "by an update-timestamp token."
        ),
        methods=("POST",),
        route_names=("training_update",),
        all_permissions=("web.manage_training",),
        scope_rule="publication_scope",
    ),
    "training_lifecycle": AuthorizationPolicy(
        key="training_lifecycle",
        access="permission_protected",
        description=(
            "Publish, schedule, unpublish, archive, or restore one training "
            "item. Re-authorizes audience selectors before go-live."
        ),
        methods=("POST",),
        route_names=("training_lifecycle",),
        all_permissions=("web.manage_training",),
        scope_rule="publication_scope",
    ),
    "training_duplicate_version": AuthorizationPolicy(
        key="training_duplicate_version",
        access="permission_protected",
        description=(
            "Fork a new draft version of published or archived training so "
            "historical learner progress stays attached to the prior version."
        ),
        methods=("POST",),
        route_names=("training_duplicate_version",),
        all_permissions=("web.manage_training",),
        scope_rule="publication_scope",
    ),
    "training_recipient_search": AuthorizationPolicy(
        key="training_recipient_search",
        access="permission_protected",
        description=(
            "Typeahead for individual training recipients, bounded by the "
            "actor's administered users."
        ),
        methods=("GET",),
        route_names=("training_recipient_search",),
        all_permissions=("web.manage_training",),
        scope_rule="delegated_user_scope",
        auth_behavior="json",
    ),
    "training_media_manager": AuthorizationPolicy(
        key="training_media_manager",
        access="permission_protected",
        description="Manage one training item's primary media and attachments.",
        methods=("GET",),
        route_names=("training_media_manager",),
        all_permissions=("web.manage_training",),
        scope_rule="office_tree_scope",
    ),
    "training_media_upload": AuthorizationPolicy(
        key="training_media_upload",
        access="permission_protected",
        description="Upload primary media or an attachment to a draft training item.",
        methods=("POST",),
        route_names=("training_media_upload",),
        all_permissions=("web.manage_training",),
        scope_rule="office_tree_scope",
        auth_behavior="json",
    ),
    "training_media_replace": AuthorizationPolicy(
        key="training_media_replace",
        access="permission_protected",
        description="Replace one stored training file on a draft.",
        methods=("POST",),
        route_names=("training_media_replace",),
        all_permissions=("web.manage_training",),
        scope_rule="office_tree_scope",
        auth_behavior="json",
    ),
    "training_media_remove": AuthorizationPolicy(
        key="training_media_remove",
        access="permission_protected",
        description="Remove one training file from a draft.",
        methods=("POST",),
        route_names=("training_media_remove",),
        all_permissions=("web.manage_training",),
        scope_rule="office_tree_scope",
    ),
    "training_media_reorder": AuthorizationPolicy(
        key="training_media_reorder",
        access="permission_protected",
        description="Set the display order of one training item's attachments.",
        methods=("POST",),
        route_names=("training_media_reorder",),
        all_permissions=("web.manage_training",),
        scope_rule="office_tree_scope",
    ),
    "training_progress": AuthorizationPolicy(
        key="training_progress",
        access="authenticated",
        description=(
            "Learner progress mutation for one visible training item. "
            "Always bound to the authenticated user."
        ),
        methods=("POST",),
        route_names=("training_progress",),
        scope_rule="training_audience_scope",
    ),
    "training_quiz_submit": AuthorizationPolicy(
        key="training_quiz_submit",
        access="authenticated",
        description="Submit one quiz attempt for a visible training quiz.",
        methods=("POST",),
        route_names=("training_quiz_submit",),
        scope_rule="training_audience_scope",
    ),
    "training_session_register": AuthorizationPolicy(
        key="training_session_register",
        access="authenticated",
        description="Register or cancel registration for a live training session.",
        methods=("POST",),
        route_names=("training_session_register",),
        scope_rule="training_audience_scope",
    ),
    "training_certificate": AuthorizationPolicy(
        key="training_certificate",
        access="authenticated",
        description="Download an approved training certificate for the learner.",
        methods=("GET",),
        route_names=("training_certificate",),
        scope_rule="training_audience_scope",
    ),
    "training_certificate_verify": AuthorizationPolicy(
        key="training_certificate_verify",
        access="public",
        description=(
            "Public verification of a training certificate by QR / UUID "
            "(HTML page or JSON for external providers)."
        ),
        methods=("GET",),
        route_names=("training_certificate_verify",),
        allow_incomplete_profile=True,
        auth_behavior="json",
    ),
    "training_quiz_save": AuthorizationPolicy(
        key="training_quiz_save",
        access="permission_protected",
        description="Save quiz definition on a draft training item.",
        methods=("POST",),
        route_names=("training_quiz_save",),
        all_permissions=("web.manage_training",),
        scope_rule="office_tree_scope",
    ),
    "training_session_save": AuthorizationPolicy(
        key="training_session_save",
        access="permission_protected",
        description="Save live-session schedule on a draft training item.",
        methods=("POST",),
        route_names=("training_session_save",),
        all_permissions=("web.manage_training",),
        scope_rule="office_tree_scope",
    ),
    "training_modules_save": AuthorizationPolicy(
        key="training_modules_save",
        access="permission_protected",
        description="Save course module ordering on a draft training course.",
        methods=("POST",),
        route_names=("training_modules_save",),
        all_permissions=("web.manage_training",),
        scope_rule="office_tree_scope",
    ),
    "training_progress_correct": AuthorizationPolicy(
        key="training_progress_correct",
        access="permission_protected",
        description=(
            "Admin correction of learner progress or live-session attendance "
            "with a required reason."
        ),
        methods=("POST",),
        route_names=("training_progress_correct",),
        all_permissions=("web.manage_training",),
        scope_rule="office_tree_scope",
    ),
    "training_certificate_issue": AuthorizationPolicy(
        key="training_certificate_issue",
        access="permission_protected",
        description=(
            "Issue a certificate of completion to a scoped learner who has "
            "completed the training."
        ),
        methods=("POST",),
        route_names=("training_certificate_issue",),
        all_permissions=("web.manage_training",),
        scope_rule="office_tree_scope",
    ),
    "training_certificate_approve": AuthorizationPolicy(
        key="training_certificate_approve",
        access="permission_protected",
        description="Approve a pending training certificate for a scoped learner.",
        methods=("POST",),
        route_names=("training_certificate_approve",),
        all_permissions=("web.manage_training",),
        scope_rule="office_tree_scope",
    ),
    "marketing_library": AuthorizationPolicy(
        key="marketing_library",
        access="authenticated",
        description=(
            "Marketing resources library for the signed-in user. Audience is "
            "resolved server-side; filters can only narrow the visible set."
        ),
        methods=("GET",),
        route_names=("marketing_resources",),
        scope_rule="publication_scope",
    ),
    "marketing_detail": AuthorizationPolicy(
        key="marketing_detail",
        access="authenticated",
        description=(
            "One marketing asset by id. Authorized by the same audience "
            "predicate as the library; superseded versions redirect to current."
        ),
        methods=("GET",),
        route_names=("marketing_resource_detail",),
        scope_rule="publication_scope",
    ),
    "marketing_export": AuthorizationPolicy(
        key="marketing_export",
        access="authenticated",
        description=(
            "Stream one approved marketing export from protected storage after "
            "re-checking audience visibility."
        ),
        methods=("GET",),
        route_names=("marketing_resource_export",),
        scope_rule="publication_scope",
    ),
    "marketing_preview": AuthorizationPolicy(
        key="marketing_preview",
        access="authenticated",
        description=(
            "Stream a marketing preview or derivative after re-checking "
            "audience visibility."
        ),
        methods=("GET",),
        route_names=("marketing_resource_preview",),
        scope_rule="publication_scope",
    ),
    "marketing_source": AuthorizationPolicy(
        key="marketing_source",
        access="permission_protected",
        description=(
            "Stream an editable marketing source file. Requires the source "
            "download grant and manage scope on the owning office."
        ),
        methods=("GET",),
        route_names=("marketing_resource_source",),
        all_permissions=("web.download_marketing_sources",),
        scope_rule="publication_scope",
    ),
    "marketing_new": AuthorizationPolicy(
        key="marketing_new",
        access="permission_protected",
        description="Open an empty marketing asset workspace within the actor's grant.",
        methods=("GET",),
        route_names=("marketing_new",),
        all_permissions=("web.manage_marketing_resources",),
        scope_rule="publication_scope",
    ),
    "marketing_edit": AuthorizationPolicy(
        key="marketing_edit",
        access="permission_protected",
        description=(
            "Open one marketing asset in the workspace. Loaded through the "
            "actor's scoped queryset, so an out-of-scope id is a 404."
        ),
        methods=("GET",),
        route_names=("marketing_edit",),
        all_permissions=("web.manage_marketing_resources",),
        scope_rule="publication_scope",
    ),
    "marketing_create": AuthorizationPolicy(
        key="marketing_create",
        access="permission_protected",
        description="Create one marketing draft. Publication is a separate action.",
        methods=("POST",),
        route_names=("marketing_create",),
        all_permissions=("web.manage_marketing_resources",),
        scope_rule="publication_scope",
    ),
    "marketing_update": AuthorizationPolicy(
        key="marketing_update",
        access="permission_protected",
        description=(
            "Save marketing copy, window, applicability, and audience. "
            "Guarded by an update-timestamp token."
        ),
        methods=("POST",),
        route_names=("marketing_update",),
        all_permissions=("web.manage_marketing_resources",),
        scope_rule="publication_scope",
    ),
    "marketing_lifecycle": AuthorizationPolicy(
        key="marketing_lifecycle",
        access="permission_protected",
        description=(
            "Publish, schedule, unpublish, archive, or restore one marketing "
            "asset. Re-authorizes audience selectors before go-live."
        ),
        methods=("POST",),
        route_names=("marketing_lifecycle",),
        all_permissions=("web.publish_marketing_resources",),
        scope_rule="publication_scope",
    ),
    "marketing_duplicate_version": AuthorizationPolicy(
        key="marketing_duplicate_version",
        access="permission_protected",
        description=(
            "Fork a new draft version of a published or archived marketing "
            "asset so superseded exports stay available for audit."
        ),
        methods=("POST",),
        route_names=("marketing_duplicate_version",),
        all_permissions=("web.manage_marketing_resources",),
        scope_rule="publication_scope",
    ),
    "marketing_recipient_search": AuthorizationPolicy(
        key="marketing_recipient_search",
        access="permission_protected",
        description=(
            "Typeahead for individual marketing recipients, bounded by the "
            "actor's administered users."
        ),
        methods=("GET",),
        route_names=("marketing_recipient_search",),
        all_permissions=("web.manage_marketing_resources",),
        scope_rule="delegated_user_scope",
        auth_behavior="json",
    ),
    "marketing_media_manager": AuthorizationPolicy(
        key="marketing_media_manager",
        access="permission_protected",
        description="Manage one marketing asset's export and source files.",
        methods=("GET",),
        route_names=("marketing_media_manager",),
        all_permissions=("web.manage_marketing_resources",),
        scope_rule="publication_scope",
    ),
    "marketing_media_upload": AuthorizationPolicy(
        key="marketing_media_upload",
        access="permission_protected",
        description="Upload an export or source file to a draft marketing asset.",
        methods=("POST",),
        route_names=("marketing_media_upload",),
        all_permissions=("web.manage_marketing_resources",),
        scope_rule="publication_scope",
        auth_behavior="json",
    ),
    "marketing_media_replace": AuthorizationPolicy(
        key="marketing_media_replace",
        access="permission_protected",
        description="Replace one stored marketing file on a draft.",
        methods=("POST",),
        route_names=("marketing_media_replace",),
        all_permissions=("web.manage_marketing_resources",),
        scope_rule="publication_scope",
        auth_behavior="json",
    ),
    "marketing_media_remove": AuthorizationPolicy(
        key="marketing_media_remove",
        access="permission_protected",
        description="Remove one marketing file from a draft.",
        methods=("POST",),
        route_names=("marketing_media_remove",),
        all_permissions=("web.manage_marketing_resources",),
        scope_rule="publication_scope",
    ),
    "marketing_media_reorder": AuthorizationPolicy(
        key="marketing_media_reorder",
        access="permission_protected",
        description="Set the display order of one marketing asset's export files.",
        methods=("POST",),
        route_names=("marketing_media_reorder",),
        all_permissions=("web.manage_marketing_resources",),
        scope_rule="publication_scope",
    ),
    "documents_forms": AuthorizationPolicy(
        key="documents_forms",
        access="authenticated",
        description=(
            "Documents and forms library for the signed-in user. Audience and "
            "jurisdiction are resolved server-side; filters can only narrow "
            "the visible set."
        ),
        methods=("GET",),
        route_names=("documents_forms",),
        scope_rule="self_only",
    ),
    "document_detail": AuthorizationPolicy(
        key="document_detail",
        access="authenticated",
        description=(
            "One document version by id. Authorized by the same audience "
            "predicate as the library; superseded versions redirect to current."
        ),
        methods=("GET",),
        route_names=("document_detail",),
        scope_rule="self_only",
    ),
    "document_file": AuthorizationPolicy(
        key="document_file",
        access="authenticated",
        description=(
            "Stream one approved document file from protected storage after "
            "re-checking current-version visibility."
        ),
        methods=("GET",),
        route_names=("document_file",),
        scope_rule="self_only",
    ),
    "document_admin_new": AuthorizationPolicy(
        key="document_admin_new",
        access="permission_protected",
        description="Open an empty document workspace within the actor's grant.",
        methods=("GET",),
        route_names=("document_admin_new",),
        all_permissions=("web.manage_documents",),
        scope_rule="publication_scope",
    ),
    "document_admin_edit": AuthorizationPolicy(
        key="document_admin_edit",
        access="permission_protected",
        description=(
            "Open one document version in the workspace. Loaded through the "
            "actor's scoped queryset, so an out-of-scope id is a 404."
        ),
        methods=("GET",),
        route_names=("document_admin_edit",),
        all_permissions=("web.manage_documents",),
        scope_rule="publication_scope",
    ),
    "document_admin_create": AuthorizationPolicy(
        key="document_admin_create",
        access="permission_protected",
        description="Create one document family and first draft version.",
        methods=("POST",),
        route_names=("document_admin_create",),
        all_permissions=("web.manage_documents",),
        scope_rule="publication_scope",
    ),
    "document_admin_update": AuthorizationPolicy(
        key="document_admin_update",
        access="permission_protected",
        description=(
            "Save document copy, window, applicability, and audience. "
            "Guarded by an update-timestamp token."
        ),
        methods=("POST",),
        route_names=("document_admin_update",),
        all_permissions=("web.manage_documents",),
        scope_rule="publication_scope",
    ),
    "document_admin_lifecycle": AuthorizationPolicy(
        key="document_admin_lifecycle",
        access="permission_protected",
        description=(
            "Publish, schedule, or retire one document version. Publish and "
            "retire are re-checked in the service against their own grants."
        ),
        methods=("POST",),
        route_names=("document_admin_lifecycle",),
        any_permissions=("web.publish_documents", "web.retire_documents"),
        scope_rule="publication_scope",
    ),
    "document_admin_duplicate": AuthorizationPolicy(
        key="document_admin_duplicate",
        access="permission_protected",
        description=(
            "Fork a new draft version of a document family so published "
            "files stay available for audit."
        ),
        methods=("POST",),
        route_names=("document_admin_duplicate",),
        all_permissions=("web.manage_documents",),
        scope_rule="publication_scope",
    ),
    "document_admin_recipient_search": AuthorizationPolicy(
        key="document_admin_recipient_search",
        access="permission_protected",
        description=(
            "Typeahead for individual document recipients, bounded by the "
            "actor's administered users."
        ),
        methods=("GET",),
        route_names=("document_admin_recipient_search",),
        all_permissions=("web.manage_documents",),
        scope_rule="delegated_user_scope",
        auth_behavior="json",
    ),
    "document_admin_media": AuthorizationPolicy(
        key="document_admin_media",
        access="permission_protected",
        description="Manage one document version's protected files.",
        methods=("GET",),
        route_names=("document_admin_media",),
        all_permissions=("web.manage_documents",),
        scope_rule="publication_scope",
    ),
    "document_admin_media_upload": AuthorizationPolicy(
        key="document_admin_media_upload",
        access="permission_protected",
        description="Upload a file to a draft document version.",
        methods=("POST",),
        route_names=("document_admin_media_upload",),
        all_permissions=("web.manage_documents",),
        scope_rule="publication_scope",
        auth_behavior="json",
    ),
    "document_admin_media_replace": AuthorizationPolicy(
        key="document_admin_media_replace",
        access="permission_protected",
        description="Replace one stored file on a draft document.",
        methods=("POST",),
        route_names=("document_admin_media_replace",),
        all_permissions=("web.manage_documents",),
        scope_rule="publication_scope",
        auth_behavior="json",
    ),
    "document_admin_media_remove": AuthorizationPolicy(
        key="document_admin_media_remove",
        access="permission_protected",
        description="Deactivate one draft document file without deleting storage.",
        methods=("POST",),
        route_names=("document_admin_media_remove",),
        all_permissions=("web.manage_documents",),
        scope_rule="publication_scope",
    ),
    "document_admin_media_reorder": AuthorizationPolicy(
        key="document_admin_media_reorder",
        access="permission_protected",
        description="Set the display order of one document version's files.",
        methods=("POST",),
        route_names=("document_admin_media_reorder",),
        all_permissions=("web.manage_documents",),
        scope_rule="publication_scope",
    ),
    "document_admin_file": AuthorizationPolicy(
        key="document_admin_file",
        access="permission_protected",
        description=(
            "Stream one document file for administrators after re-checking "
            "manage scope. Uses the same protected storage as consumer "
            "downloads."
        ),
        methods=("GET",),
        route_names=("document_admin_file",),
        all_permissions=("web.manage_documents",),
        scope_rule="publication_scope",
    ),
    "policies_compliance": AuthorizationPolicy(
        key="policies_compliance",
        access="authenticated",
        description=(
            "Policy library for the signed-in user. Audience and jurisdiction "
            "are resolved server-side; filters can only narrow the visible set."
        ),
        methods=("GET",),
        route_names=("policies_compliance",),
        scope_rule="self_only",
    ),
    "policy_detail": AuthorizationPolicy(
        key="policy_detail",
        access="authenticated",
        description="Policy detail for an audience-visible published version.",
        methods=("GET",),
        route_names=("policy_detail",),
        scope_rule="self_only",
    ),
    "policy_acknowledge": AuthorizationPolicy(
        key="policy_acknowledge",
        access="authenticated",
        description="Acknowledge one audience-visible published policy version.",
        methods=("POST",),
        route_names=("policy_acknowledge",),
        scope_rule="self_only",
    ),
    "policy_document_file": AuthorizationPolicy(
        key="policy_document_file",
        access="authenticated",
        description="Stream one ready policy document after audience re-check.",
        methods=("GET",),
        route_names=("policy_document_file",),
        scope_rule="self_only",
    ),
    "policy_admin_new": AuthorizationPolicy(
        key="policy_admin_new",
        access="permission_protected",
        description="Blank compliance policy workspace.",
        methods=("GET",),
        route_names=("policy_admin_new",),
        all_permissions=("web.manage_policies",),
        scope_rule="publication_scope",
    ),
    "policy_admin_edit": AuthorizationPolicy(
        key="policy_admin_edit",
        access="permission_protected",
        description="Edit one scoped policy draft or review row.",
        methods=("GET",),
        route_names=("policy_admin_edit",),
        all_permissions=("web.manage_policies",),
        scope_rule="publication_scope",
    ),
    "policy_admin_create": AuthorizationPolicy(
        key="policy_admin_create",
        access="permission_protected",
        description="Create a new policy draft in scope.",
        methods=("POST",),
        route_names=("policy_admin_create",),
        all_permissions=("web.manage_policies",),
        scope_rule="publication_scope",
    ),
    "policy_admin_update": AuthorizationPolicy(
        key="policy_admin_update",
        access="permission_protected",
        description="Save one mutable policy draft in scope.",
        methods=("POST",),
        route_names=("policy_admin_update",),
        all_permissions=("web.manage_policies",),
        scope_rule="publication_scope",
    ),
    "policy_admin_lifecycle": AuthorizationPolicy(
        key="policy_admin_lifecycle",
        access="permission_protected",
        description=(
            "Submit, approve, publish, retire, or return a policy. "
            "Approve and publish grants are re-checked in the service layer."
        ),
        methods=("POST",),
        route_names=("policy_admin_lifecycle",),
        all_permissions=("web.manage_policies",),
        scope_rule="publication_scope",
    ),
    "policy_admin_duplicate": AuthorizationPolicy(
        key="policy_admin_duplicate",
        access="permission_protected",
        description="Draft the next version of a policy family.",
        methods=("POST",),
        route_names=("policy_admin_duplicate",),
        all_permissions=("web.manage_policies",),
        scope_rule="publication_scope",
    ),
    "policy_admin_file_upload": AuthorizationPolicy(
        key="policy_admin_file_upload",
        access="permission_protected",
        description="Upload a document or source file onto a mutable policy.",
        methods=("POST",),
        route_names=("policy_admin_file_upload",),
        all_permissions=("web.manage_policies",),
        scope_rule="publication_scope",
    ),
    "policy_admin_file_remove": AuthorizationPolicy(
        key="policy_admin_file_remove",
        access="permission_protected",
        description="Remove one policy file from a mutable policy.",
        methods=("POST",),
        route_names=("policy_admin_file_remove",),
        all_permissions=("web.manage_policies",),
        scope_rule="publication_scope",
    ),
    "policy_ack_report": AuthorizationPolicy(
        key="policy_ack_report",
        access="permission_protected",
        description="Scoped acknowledgement status report for mandatory policies.",
        methods=("GET",),
        route_names=("policy_ack_report",),
        any_permissions=(
            "web.view_compliance",
            "web.manage_policies",
            "web.view_policy_acknowledgements",
        ),
        scope_rule="publication_scope",
    ),
    "policy_ack_waive": AuthorizationPolicy(
        key="policy_ack_waive",
        access="permission_protected",
        description="Waive one person's acknowledgement requirement in scope.",
        methods=("POST",),
        route_names=("policy_ack_waive",),
        all_permissions=("web.waive_policy_acknowledgements",),
        scope_rule="publication_scope",
    ),
    "policy_ack_correct": AuthorizationPolicy(
        key="policy_ack_correct",
        access="permission_protected",
        description=(
            "Record a reasoned acknowledgement correction without deleting evidence."
        ),
        methods=("POST",),
        route_names=("policy_ack_correct",),
        all_permissions=("web.waive_policy_acknowledgements",),
        scope_rule="publication_scope",
    ),
    "office_resource_download": AuthorizationPolicy(
        key="office_resource_download",
        access="authenticated",
        description=(
            "Stream one resource file after re-checking the actor's own "
            "effective-resource visibility (same gate as the page)."
        ),
        methods=("GET",),
        route_names=("office_resources_download",),
        scope_rule="self_only",
    ),
    "new_agent_onboarding": AuthorizationPolicy(
        key="new_agent_onboarding",
        access="permission_protected",
        description="Render one source-derived onboarding record inside scope.",
        methods=("GET",),
        route_names=("new_agent_onboarding",),
        all_permissions=("web.view_new_agents",),
        scope_rule="administered_user_scope",
    ),
    "new_agent_onboarding_headshot": AuthorizationPolicy(
        key="new_agent_onboarding_headshot",
        access="permission_protected",
        description="Stream one scoped onboarding headshot.",
        methods=("GET",),
        route_names=("new_agent_onboarding_headshot",),
        all_permissions=("web.view_new_agents",),
        scope_rule="administered_user_scope",
    ),
    "new_agent_onboarding_owner": AuthorizationPolicy(
        key="new_agent_onboarding_owner",
        access="permission_protected",
        description="Assign the operational owner of one scoped onboarding case.",
        methods=("POST",),
        route_names=("new_agent_onboarding_owner",),
        all_permissions=("web.manage_new_agent_onboarding",),
        scope_rule="administered_user_scope",
    ),
    "new_agent_onboarding_tasks": AuthorizationPolicy(
        key="new_agent_onboarding_tasks",
        access="permission_protected",
        description="Create or resolve an operational onboarding task.",
        methods=("POST",),
        route_names=("new_agent_onboarding_tasks",),
        all_permissions=("web.manage_new_agent_onboarding",),
        scope_rule="administered_user_scope",
    ),
    "new_agent_onboarding_tools": AuthorizationPolicy(
        key="new_agent_onboarding_tools",
        access="permission_protected",
        description="Update one approved operational tool-setup state.",
        methods=("POST",),
        route_names=("new_agent_onboarding_tools",),
        all_permissions=("web.manage_new_agent_onboarding",),
        scope_rule="administered_user_scope",
    ),
    "new_agent_onboarding_contract": AuthorizationPolicy(
        key="new_agent_onboarding_contract",
        access="permission_protected",
        description=(
            "Initiate a contract for one scoped onboarding case through the "
            "contract domain."
        ),
        methods=("POST",),
        route_names=("new_agent_onboarding_contract",),
        all_permissions=(
            "web.manage_new_agent_onboarding",
            "contract.manage_agent_contracts",
        ),
        scope_rule="administered_user_scope",
    ),
    "new_agent_onboarding_handoff": AuthorizationPolicy(
        key="new_agent_onboarding_handoff",
        access="permission_protected",
        description=(
            "Re-send a failed office handoff for one scoped onboarding case to "
            "the office's current Branch Admin."
        ),
        methods=("POST",),
        route_names=("new_agent_onboarding_handoff",),
        all_permissions=("web.manage_new_agent_onboarding",),
        scope_rule="source_service_reauthorization",
    ),
    "new_agent_onboarding_notice": AuthorizationPolicy(
        key="new_agent_onboarding_notice",
        access="permission_protected",
        description="Delegate an eligible notice resend to its source domain.",
        methods=("POST",),
        route_names=("new_agent_onboarding_notice",),
        all_permissions=("web.manage_new_agent_onboarding",),
        scope_rule="source_service_reauthorization",
    ),
    "quick_access_new": AuthorizationPolicy(
        key="quick_access_new",
        access="permission_protected",
        description=(
            "Render the blank Quick Access link form. Audience choices are "
            "built from the actor's own office scope."
        ),
        methods=("GET",),
        route_names=("quick_access_new",),
        all_permissions=("web.manage_quick_access",),
        scope_rule="quick_access_audience_scope",
    ),
    "quick_access_edit": AuthorizationPolicy(
        key="quick_access_edit",
        access="permission_protected",
        description=(
            "Render one Quick Access link. The link is resolved through the "
            "actor's manageable queryset, so an out-of-scope id is a 404."
        ),
        methods=("GET",),
        route_names=("quick_access_edit",),
        all_permissions=("web.manage_quick_access",),
        scope_rule="quick_access_link_scope",
    ),
    "quick_access_create": AuthorizationPolicy(
        key="quick_access_create",
        access="permission_protected",
        description=(
            "Create a Quick Access link. Company-wide audiences additionally "
            "require web.manage_company_quick_access."
        ),
        methods=("POST",),
        route_names=("quick_access_create",),
        all_permissions=("web.manage_quick_access",),
        scope_rule="quick_access_audience_scope",
    ),
    "quick_access_update": AuthorizationPolicy(
        key="quick_access_update",
        access="permission_protected",
        description=(
            "Update one Quick Access link, its audience, and its destination."
        ),
        methods=("POST",),
        route_names=("quick_access_update",),
        all_permissions=("web.manage_quick_access",),
        scope_rule="quick_access_link_scope",
    ),
    "quick_access_state": AuthorizationPolicy(
        key="quick_access_state",
        access="permission_protected",
        description=(
            "Activate, deactivate, archive, or restore one Quick Access link. "
            "Records are never deleted."
        ),
        methods=("POST",),
        route_names=("quick_access_state",),
        all_permissions=("web.manage_quick_access",),
        scope_rule="quick_access_link_scope",
    ),
    "quick_access_reorder": AuthorizationPolicy(
        key="quick_access_reorder",
        access="permission_protected",
        description=(
            "Rewrite the Quick Access panel order. Every submitted link must "
            "be manageable by the actor; unmanaged links keep their position."
        ),
        methods=("POST",),
        route_names=("quick_access_reorder",),
        all_permissions=("web.manage_quick_access",),
        scope_rule="quick_access_link_scope",
    ),
    "quick_access_click": AuthorizationPolicy(
        key="quick_access_click",
        access="authenticated",
        description=(
            "Record that the signed-in reader opened one of their own Quick "
            "Access launchers. Answers 204 to every caller: the key is "
            "resolved against the reader's own visible links, so it can "
            "neither confirm nor deny another office's configuration."
        ),
        methods=("POST",),
        route_names=("quick_access_click",),
        scope_rule="self_only",
        auth_behavior="json",
    ),
    "dashboard": AuthorizationPolicy(
        key="dashboard",
        access="authenticated",
        description=(
            "Render the hub shell for incomplete agents and deferred widgets "
            "only after required setup is complete."
        ),
        methods=("GET",),
        route_names=("dashboard",),
        scope_rule="self_only",
        allow_incomplete_profile=True,
    ),
    "action_items_queue": AuthorizationPolicy(
        key="action_items_queue",
        access="authenticated",
        description=(
            "Render the full filtered action-item queue for the signed-in "
            "user. Re-derives items from source records; never trusts a "
            "stale dashboard row id."
        ),
        methods=("GET",),
        route_names=("action_items_queue",),
        scope_rule="self_only",
    ),
    "notifications": AuthorizationPolicy(
        key="notifications",
        access="authenticated",
        description=(
            "Render the signed-in reader's own notification centre. Never "
            "accepts a recipient identifier: the queryset starts from "
            "request.user and there is no path that widens it."
        ),
        methods=("GET",),
        route_names=("notifications",),
        scope_rule="self_only",
    ),
    "notification_state": AuthorizationPolicy(
        key="notification_state",
        access="authenticated",
        description=(
            "Mark one of the reader's own notifications read, unread, or "
            "archived. The opaque id is resolved through their own queryset, "
            "so somebody else's id is indistinguishable from a missing one."
        ),
        methods=("POST",),
        route_names=("notification_state",),
        scope_rule="self_only",
    ),
    "notification_read_all": AuthorizationPolicy(
        key="notification_read_all",
        access="authenticated",
        description=(
            "Clear the reader's own unread notifications. Mandatory items are "
            "excluded and stay for individual acknowledgement."
        ),
        methods=("POST",),
        route_names=("notification_read_all",),
        scope_rule="self_only",
    ),
    "notification_preferences": AuthorizationPolicy(
        key="notification_preferences",
        access="authenticated",
        description=(
            "Render the signed-in reader's own notification settings. Reads "
            "and writes one row, keyed by request.user, and offers no control "
            "over mandatory legal, compliance, or security notices."
        ),
        methods=("GET",),
        route_names=("notification_preferences",),
        scope_rule="self_only",
    ),
    "notification_preferences_submit": AuthorizationPolicy(
        key="notification_preferences_submit",
        access="authenticated",
        description=(
            "Persist the signed-in reader's own channel choices. Mandatory "
            "categories have no form field, so no request can switch them off."
        ),
        methods=("POST",),
        route_names=("notification_preferences_submit",),
        scope_rule="self_only",
    ),
    "notification_summary": AuthorizationPolicy(
        key="notification_summary",
        access="authenticated",
        description=(
            "Unread counts for the header badge, polled by the shell. Answers "
            "only about the caller; there is no cross-user or office count."
        ),
        methods=("GET",),
        route_names=("notification_summary",),
        scope_rule="self_only",
        auth_behavior="json",
    ),
    "search_suggestions": AuthorizationPolicy(
        key="search_suggestions",
        access="authenticated",
        description=(
            "Grouped global-search results for the header dialog. Every source "
            "is asked through its own domain's scoped queryset, so a result "
            "the reader could not open on its own page cannot appear here — "
            "including in a snippet or a count. Sources whose permission the "
            "reader lacks are never queried and never named. Rate limited per "
            "actor; answers JSON because it is polled while typing."
        ),
        methods=("GET",),
        route_names=("search_suggestions",),
        scope_rule="search_provider_scope",
        auth_behavior="json",
    ),
    "search_page": AuthorizationPolicy(
        key="search_page",
        access="authenticated",
        description=(
            "Full global-search results. Same aggregator as the dialog, so the "
            "two cannot disagree about what this reader may see; every "
            "destination still re-enforces its own policy when followed."
        ),
        methods=("GET",),
        route_names=("search",),
        scope_rule="search_provider_scope",
    ),
    "design_system": AuthorizationPolicy(
        key="design_system",
        access="authenticated",
        description="Render the internal ONEST component catalog.",
        methods=("GET",),
        route_names=("design_system",),
        scope_rule="self_only",
    ),
    "coming_soon": AuthorizationPolicy(
        key="coming_soon",
        access="authenticated",
        description="Render a placeholder hub section page.",
        methods=("GET",),
        route_names=("coming_soon",),
        scope_rule="self_only",
    ),
    "activity_timeline": AuthorizationPolicy(
        key="activity_timeline",
        access="permission_protected",
        description="Cursor-paginated activity timeline for one authorized record.",
        methods=("GET",),
        route_names=("activity_timeline",),
        all_permissions=("audit.can_view_activity_timeline",),
        scope_rule="none",
        auth_behavior="json",
        surface_type="route",
    ),
    "report_catalog": AuthorizationPolicy(
        key="report_catalog",
        access="permission_protected",
        description="List operational reports the actor is entitled to.",
        methods=("GET",),
        route_names=("report_catalog",),
        all_permissions=("web.view_reports",),
        scope_rule="user_office_scope",
    ),
    "report_detail": AuthorizationPolicy(
        key="report_detail",
        access="permission_protected",
        description=(
            "Render one operational report. Per-report permissions and scope "
            "are enforced again inside the calculator."
        ),
        methods=("GET",),
        route_names=("report_detail",),
        all_permissions=("web.view_reports",),
        scope_rule="user_office_scope",
    ),
    "report_export_create": AuthorizationPolicy(
        key="report_export_create",
        access="permission_protected",
        description="Queue a scoped report export job.",
        methods=("POST",),
        route_names=("report_export_create",),
        all_permissions=("web.view_reports", "web.export_reports"),
        scope_rule="user_office_scope",
        auth_behavior="json",
    ),
    "report_export_status": AuthorizationPolicy(
        key="report_export_status",
        access="permission_protected",
        description="Poll progress for a report export the actor requested.",
        methods=("GET",),
        route_names=("report_export_status",),
        all_permissions=("web.view_reports", "web.export_reports"),
        scope_rule="self_only",
        auth_behavior="json",
    ),
    "report_export_download": AuthorizationPolicy(
        key="report_export_download",
        access="permission_protected",
        description=(
            "Stream a ready report export from protected storage after "
            "re-checking entitlement and expiry."
        ),
        methods=("GET",),
        route_names=("report_export_download",),
        all_permissions=("web.view_reports", "web.export_reports"),
        scope_rule="self_only",
    ),
}

ROUTE_POLICIES.update(
    {
        operations_policy_key(destination): AuthorizationPolicy(
            key=operations_policy_key(destination),
            access="permission_protected",
            description=f"Render the {destination.label} administrative destination.",
            methods=("GET",),
            route_names=(destination.route_name,),
            all_permissions=(destination.permission,),
            scope_rule=destination.scope_rule,
        )
        for destination in OPERATIONS_DESTINATIONS
    }
)

ROUTE_POLICIES["operations_admin_contract_templates"] = AuthorizationPolicy(
    key="operations_admin_contract_templates",
    access="permission_protected",
    description="Render the governed contract-template administration destination.",
    methods=("GET",),
    route_names=("admin_contract_templates",),
    all_permissions=("contract.manage_contract_templates",),
    scope_rule="user_office_scope",
)
ROUTE_POLICIES["contract_template_admin"] = AuthorizationPolicy(
    key="contract_template_admin",
    access="permission_protected",
    description="Render the contract-template administration queue.",
    methods=("GET",),
    route_names=("admin_contract_templates",),
    all_permissions=("contract.manage_contract_templates",),
    scope_rule="user_office_scope",
)
ROUTE_POLICIES["contract_template_create"] = AuthorizationPolicy(
    key="contract_template_create",
    access="permission_protected",
    description="Create a draft contract template family and first version.",
    methods=("POST",),
    route_names=("contract_template_create",),
    all_permissions=("contract.manage_contract_templates",),
    scope_rule="user_office_scope",
)
ROUTE_POLICIES["contract_template_workspace"] = AuthorizationPolicy(
    key="contract_template_workspace",
    access="permission_protected",
    description="Render one draft or published contract template version workspace.",
    methods=("GET",),
    route_names=("contract_template_workspace",),
    any_permissions=(
        "contract.manage_contract_templates",
        "contract.approve_contract_templates",
    ),
    scope_rule="user_office_scope",
)
ROUTE_POLICIES["contract_template_update"] = AuthorizationPolicy(
    key="contract_template_update",
    access="permission_protected",
    description="Save a contract template draft version.",
    methods=("POST",),
    route_names=("contract_template_update",),
    all_permissions=("contract.manage_contract_templates",),
    scope_rule="user_office_scope",
)
ROUTE_POLICIES["contract_template_action"] = AuthorizationPolicy(
    key="contract_template_action",
    access="permission_protected",
    description="Preview, publish, activate, or retire a contract template version.",
    methods=("POST",),
    route_names=("contract_template_action",),
    any_permissions=(
        "contract.manage_contract_templates",
        "contract.approve_contract_templates",
    ),
    scope_rule="user_office_scope",
)
ROUTE_POLICIES["contract_template_field_layout"] = AuthorizationPolicy(
    key="contract_template_field_layout",
    access="permission_protected",
    description="Save Hub field placer layout for a contract template draft.",
    methods=("POST",),
    route_names=("contract_template_field_layout",),
    all_permissions=("contract.manage_contract_templates",),
    scope_rule="user_office_scope",
)
ROUTE_POLICIES["contract_template_source_pdf"] = AuthorizationPolicy(
    key="contract_template_source_pdf",
    access="permission_protected",
    description="Stream the protected template PDF for the Hub field placer.",
    methods=("GET",),
    route_names=("contract_template_source_pdf",),
    any_permissions=(
        "contract.manage_contract_templates",
        "contract.approve_contract_templates",
    ),
    scope_rule="user_office_scope",
)
ROUTE_POLICIES["contract_template_preview_pdf"] = AuthorizationPolicy(
    key="contract_template_preview_pdf",
    access="permission_protected",
    description="Stream the protected synthetic template preview PDF.",
    methods=("GET",),
    route_names=("contract_template_preview_pdf",),
    any_permissions=(
        "contract.manage_contract_templates",
        "contract.approve_contract_templates",
    ),
    scope_rule="user_office_scope",
)

ROUTE_POLICIES["agent_contract_admin"] = AuthorizationPolicy(
    key="agent_contract_admin",
    access="permission_protected",
    description="Render the agent-contract administration list.",
    methods=("GET",),
    route_names=("admin_agent_contracts",),
    all_permissions=("web.view_agent_contracts",),
    scope_rule="user_office_scope",
)
ROUTE_POLICIES["agent_contract_workspace"] = AuthorizationPolicy(
    key="agent_contract_workspace",
    access="permission_protected",
    description="Render one agent-contract workspace.",
    methods=("GET",),
    route_names=("agent_contract_workspace", "agent_contract_preview"),
    any_permissions=(
        "web.view_agent_contracts",
        "contract.manage_agent_contracts",
    ),
    scope_rule="user_office_scope",
)
ROUTE_POLICIES["agent_contract_manage"] = AuthorizationPolicy(
    key="agent_contract_manage",
    access="permission_protected",
    description="Create, update, validate, preview, or issue agent contracts.",
    methods=("GET", "POST"),
    route_names=(
        "agent_contract_new",
        "agent_contract_create",
        "agent_contract_update",
        "agent_contract_create_amendment",
        "agent_contract_create_replacement",
        "agent_contract_lifecycle",
        "agent_contract_recipient_search",
        "agent_contract_template_options",
        "agent_contract_validate",
    ),
    all_permissions=("contract.manage_agent_contracts",),
    scope_rule="user_office_scope",
)
ROUTE_POLICIES["agent_contract_artifact_download"] = AuthorizationPolicy(
    key="agent_contract_artifact_download",
    access="authenticated",
    description=(
        "Stream a protected contract PDF after re-checking recipient or "
        "scoped admin access. No durable URL is issued."
    ),
    methods=("GET",),
    route_names=("agent_contract_artifact_download",),
    scope_rule="assigned_or_self",
)
ROUTE_POLICIES["agent_contract_artifact_preview"] = AuthorizationPolicy(
    key="agent_contract_artifact_preview",
    access="authenticated",
    description=(
        "Inline (iframe-safe) stream of a protected contract PDF after the "
        "same access checks as download. Used by the ops preview surface."
    ),
    methods=("GET",),
    route_names=("agent_contract_artifact_preview",),
    scope_rule="assigned_or_self",
)
ROUTE_POLICIES["agent_contract_signed_pdf_verify"] = AuthorizationPolicy(
    key="agent_contract_signed_pdf_verify",
    access="authenticated",
    description=(
        "Integrity metadata for a final signed contract PDF (checksums, "
        "signature id, renderer version) without streaming private bytes."
    ),
    methods=("GET",),
    route_names=("agent_contract_signed_pdf_verify",),
    scope_rule="assigned_or_self",
)
ROUTE_POLICIES["agent_contract_company_sign"] = AuthorizationPolicy(
    key="agent_contract_company_sign",
    access="authenticated",
    description=(
        "Named company signatory ceremony for an agent contract. The view "
        "re-checks company_signatory identity; managers without that "
        "assignment cannot complete the pad."
    ),
    methods=("GET", "POST"),
    route_names=(
        "agent_contract_company_sign",
        "agent_contract_company_sign_complete",
        "agent_contract_company_sign_preview",
    ),
    scope_rule="self_only",
)
ROUTE_POLICIES["my_contract"] = AuthorizationPolicy(
    key="my_contract",
    access="authenticated",
    description=(
        "Self-service My Contract page for the signed-in recipient. "
        "Never accepts an agent id from the client; optional version "
        "query is re-checked against the recipient's own family."
    ),
    methods=("GET",),
    route_names=("my_contract",),
    scope_rule="self_only",
)
ROUTE_POLICIES["my_contract_artifact_preview"] = AuthorizationPolicy(
    key="my_contract_artifact_preview",
    access="authenticated",
    description=(
        "Inline preview stream for the recipient's own contract PDF. "
        "Re-checks self-only queryset on every request."
    ),
    methods=("GET",),
    route_names=("my_contract_artifact_preview",),
    scope_rule="self_only",
)
ROUTE_POLICIES["my_contract_signed_pdf_verify"] = AuthorizationPolicy(
    key="my_contract_signed_pdf_verify",
    access="authenticated",
    description=(
        "Recipient integrity check for their own final signed PDF metadata. "
        "Does not expose private PDF bytes."
    ),
    methods=("GET",),
    route_names=("my_contract_signed_pdf_verify",),
    scope_rule="self_only",
)
ROUTE_POLICIES["my_contract_sign"] = AuthorizationPolicy(
    key="my_contract_sign",
    access="authenticated",
    description=(
        "Recipient signing ceremony for the authenticated agent's own contract. "
        "Admins cannot sign on an agent's behalf through this route."
    ),
    methods=("GET", "POST"),
    route_names=("my_contract_sign",),
    scope_rule="self_only",
)
ROUTE_POLICIES["my_contract_sign_status"] = AuthorizationPolicy(
    key="my_contract_sign_status",
    access="authenticated",
    description=(
        "Poll whether a durable signature record exists for the recipient's "
        "signing ceremony success gate."
    ),
    methods=("GET",),
    route_names=("my_contract_sign_status",),
    scope_rule="self_only",
)
ROUTE_POLICIES["my_contract_sign_complete"] = AuthorizationPolicy(
    key="my_contract_sign_complete",
    access="authenticated",
    description=(
        "Commit Hub-native signature appearance, seal, and durable signature "
        "record for the authenticated recipient."
    ),
    methods=("POST",),
    route_names=("my_contract_sign_complete",),
    scope_rule="self_only",
)

NON_ROUTE_SURFACES: tuple[AuthorizationPolicy, ...] = (
    AuthorizationPolicy(
        key="admin_prefix",
        access="permission_protected",
        description="Django admin site and model endpoints.",
        methods=("GET", "POST"),
        path_prefixes=("/admin/",),
        all_permissions=("admin.access_admin",),
        scope_rule="admin_queryset_scope",
        surface_type="path_prefix",
    ),
    AuthorizationPolicy(
        key="allauth_accounts_prefix",
        access="public",
        description="Third-party allauth auth endpoints under /accounts/.",
        methods=("GET", "POST"),
        path_prefixes=("/accounts/",),
        surface_type="path_prefix",
    ),
    AuthorizationPolicy(
        key="user_admin_reset_onboarding",
        access="permission_protected",
        description="Admin bulk reset of onboarding state.",
        methods=("POST",),
        all_permissions=("user.change_user",),
        scope_rule="user_office_scope_all_objects",
        surface_type="admin_action",
    ),
    AuthorizationPolicy(
        key="audit_admin_replay_selected",
        access="permission_protected",
        description="Admin bulk replay of domain events.",
        methods=("POST",),
        all_permissions=("audit.can_replay_events",),
        scope_rule="audit_event_scope",
        surface_type="admin_action",
    ),
    AuthorizationPolicy(
        key="audit_admin_replay_selected_deliveries",
        access="permission_protected",
        description="Admin bulk replay of event deliveries.",
        methods=("POST",),
        all_permissions=("audit.can_replay_events",),
        scope_rule="audit_event_scope",
        surface_type="admin_action",
    ),
    AuthorizationPolicy(
        key="audit_task_replay_event",
        access="permission_protected",
        description="Background replay task with initiator revalidation.",
        methods=("TASK",),
        all_permissions=("audit.can_replay_events",),
        scope_rule="initiator_revalidation",
        surface_type="task",
    ),
)


def inventory_rows() -> list[dict[str, Any]]:
    policies = list(ROUTE_POLICIES.values()) + list(NON_ROUTE_SURFACES)
    return [asdict(policy) for policy in policies]


def get_authorization_policy(view_func) -> AuthorizationPolicy | None:
    return getattr(view_func, "_authorization_policy", None)


def _has_permissions(user, any_permissions, all_permissions):
    """Fail-closed capability check via the reviewed permission catalog."""
    return matches_permission_check(
        user,
        any_permissions=tuple(any_permissions),
        all_permissions=tuple(all_permissions),
    )


def _log_denial(
    request: HttpRequest,
    *,
    policy: AuthorizationPolicy,
    reason: str,
    status_code: int,
) -> None:
    request_id = getattr(request, "audit_request_id", "")
    log_event(
        "security.authorization.denied",
        actor=actor_from_user(getattr(request, "user", None)),
        target=AuditTarget(
            target_type="endpoint",
            target_label=request.path,
            target_snapshot={
                "policy": policy.key,
                "access": policy.access,
                "methods": list(policy.methods),
            },
        ),
        outcome=AuditEvent.Outcome.DENIED,
        source="request",
        channel=request.method or "",
        reason=reason,
        metadata={"request_id": request_id, "status_code": status_code},
    )
    logger.info(
        (
            "authorization_denied policy=%s path=%s method=%s "
            "status=%s request_id=%s reason=%s"
        ),
        policy.key,
        request.path,
        request.method,
        status_code,
        request_id,
        reason,
    )


def _json_denial(status_code: int, code: str, request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        {
            "error": code,
            "requestId": getattr(request, "audit_request_id", ""),
        },
        status=status_code,
    )


def _unauthenticated_response(
    request: HttpRequest, policy: AuthorizationPolicy
) -> HttpResponse:
    if policy.auth_behavior == "json":
        return _json_denial(401, "authentication_required", request)
    return unauthenticated_redirect(request)


def unauthenticated_redirect(
    request: HttpRequest, *, login_url: str | None = None
) -> HttpResponse:
    """Redirect safely, marking only interrupted Inertia sessions as expired."""

    destination = login_url
    if destination is None and request.headers.get("X-Inertia") == "true":
        destination = f"{reverse('login')}?reason=session-expired"
    return redirect_to_login(request.get_full_path(), login_url=destination)


def enforce_policy(policy_key: str):
    policy = ROUTE_POLICIES[policy_key]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request: HttpRequest, *args, **kwargs):
            user = request.user
            if policy.access == "public":
                return view_func(request, *args, **kwargs)
            if not user.is_authenticated:
                _log_denial(
                    request,
                    policy=policy,
                    reason="authentication_required",
                    status_code=401,
                )
                return _unauthenticated_response(request, policy)
            if policy.access == "permission_protected" and not _has_permissions(
                user,
                policy.any_permissions,
                policy.all_permissions,
            ):
                _log_denial(
                    request,
                    policy=policy,
                    reason="missing_permissions",
                    status_code=policy.denial_status,
                )
                if policy.auth_behavior == "json":
                    return _json_denial(
                        policy.denial_status, "permission_denied", request
                    )
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        wrapped_view = cast(Any, _wrapped)
        wrapped_view._authorization_policy = policy
        return wrapped_view

    return decorator


def _office_scope_q(access, *, field_name: str) -> Q:
    if access.company_wide:
        return Q()
    filters = Q()
    if access.region_keys:
        filters |= Q(
            **{f"{field_name}__region__stable_key__in": sorted(access.region_keys)}
        )
    if access.office_keys:
        filters |= Q(**{f"{field_name}__stable_key__in": sorted(access.office_keys)})
    return filters


def scope_q_for_user_offices(user, *, field_name: str) -> Q:
    return _office_scope_q(get_effective_access(user), field_name=field_name)


def scope_queryset_for_user_office(
    user,
    queryset: QuerySet,
    *,
    field_name: str,
    access=None,
) -> QuerySet:
    if getattr(user, "is_superuser", False):
        return queryset
    effective = get_effective_access(user) if access is None else access
    # Company-wide access yields an empty ``Q``, which is falsy — reading it as
    # "no scope" would hand a brokerage-wide admin an empty queryset.
    if effective.company_wide:
        return queryset
    filters = _office_scope_q(effective, field_name=field_name)
    if not filters:
        return queryset.none()
    return queryset.filter(filters)


def scope_queryset_for_offices(user, queryset: QuerySet) -> QuerySet:
    if getattr(user, "is_superuser", False):
        return queryset
    access = get_effective_access(user)
    if access.company_wide:
        return queryset
    filters = Q()
    if access.region_keys:
        filters |= Q(region__stable_key__in=sorted(access.region_keys)) | Q(
            stable_key__in=sorted(access.region_keys)
        )
    if access.office_keys:
        filters |= Q(stable_key__in=sorted(access.office_keys))
    if not filters:
        return queryset.none()
    return queryset.filter(filters)


def assert_admin_bulk_scope(
    user,
    queryset: QuerySet,
    *,
    scoped_queryset: QuerySet,
    policy_key: str,
) -> None:
    total_ids = set(queryset.values_list("pk", flat=True))
    scoped_ids = set(scoped_queryset.values_list("pk", flat=True))
    if total_ids != scoped_ids:
        policy = next(item for item in NON_ROUTE_SURFACES if item.key == policy_key)
        dummy_request = HttpRequest()
        dummy_request.user = user
        dummy_request.path = "admin-bulk-action"
        dummy_request.method = "POST"
        _log_denial(
            dummy_request,
            policy=policy,
            reason="out_of_scope_objects",
            status_code=403,
        )
        raise PermissionDenied("The selected collection contains out-of-scope objects.")


def has_admin_permission(user, *permissions: str) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    if not getattr(user, "is_staff", False):
        return False
    return matches_permission_check(user, all_permissions=tuple(permissions))


def is_explicitly_public_path(path: str) -> bool:
    return any(
        path.startswith(prefix)
        for policy in NON_ROUTE_SURFACES
        if policy.access == "public"
        for prefix in policy.path_prefixes
    )


def is_non_route_exempt_path(path: str) -> bool:
    if path.startswith("/admin/"):
        return True
    if is_explicitly_public_path(path):
        return True
    return path.startswith("/silk/")


# --- scoped room administration workspace ----------------------------------
ROUTE_POLICIES["space_administration"] = AuthorizationPolicy(
    key="space_administration",
    access="permission_protected",
    description=(
        "Scoped room administration list. Rooms are filtered to the actor's "
        "effective hierarchy before serialization; a posted office is never "
        "trusted."
    ),
    methods=("GET",),
    route_names=("space_administration",),
    all_permissions=("reservations.view_spaces",),
    scope_rule="reservation_office_scope",
)
ROUTE_POLICIES["space_administration_workspace"] = AuthorizationPolicy(
    key="space_administration_workspace",
    access="permission_protected",
    description="One room's identity, policy, schedule, blocks, and bookings.",
    methods=("GET",),
    route_names=("space_administration_workspace",),
    all_permissions=("reservations.view_spaces",),
    scope_rule="reservation_office_scope",
)
ROUTE_POLICIES["space_administration_create"] = AuthorizationPolicy(
    key="space_administration_create",
    access="permission_protected",
    description="Create a room in an office the actor administers.",
    methods=("POST",),
    route_names=("space_administration_create",),
    all_permissions=("reservations.manage_spaces",),
    scope_rule="reservation_office_scope",
)
ROUTE_POLICIES["space_administration_update"] = AuthorizationPolicy(
    key="space_administration_update",
    access="permission_protected",
    description="Edit room identity and booking policy with a stale-edit guard.",
    methods=("POST",),
    route_names=("space_administration_update",),
    all_permissions=("reservations.manage_spaces",),
    scope_rule="reservation_office_scope",
)
ROUTE_POLICIES["space_administration_activation"] = AuthorizationPolicy(
    key="space_administration_activation",
    access="permission_protected",
    description="Activate or deactivate a room after reviewing booking impact.",
    methods=("POST",),
    route_names=("space_administration_activation",),
    all_permissions=("reservations.manage_spaces",),
    scope_rule="reservation_office_scope",
)
ROUTE_POLICIES["space_administration_retire"] = AuthorizationPolicy(
    key="space_administration_retire",
    access="permission_protected",
    description="Retire a room without deleting its identity or history.",
    methods=("POST",),
    route_names=("space_administration_retire",),
    all_permissions=("reservations.manage_spaces",),
    scope_rule="reservation_office_scope",
)
ROUTE_POLICIES["space_administration_schedule"] = AuthorizationPolicy(
    key="space_administration_schedule",
    access="permission_protected",
    description="Replace a room's weekly opening hours as one atomic set.",
    methods=("POST",),
    route_names=("space_administration_schedule",),
    all_permissions=("reservations.manage_space_schedules",),
    scope_rule="reservation_office_scope",
)
ROUTE_POLICIES["space_administration_block_create"] = AuthorizationPolicy(
    key="space_administration_block_create",
    access="permission_protected",
    description="Add a maintenance or closure block through the capacity ledger.",
    methods=("POST",),
    route_names=("space_administration_block_create",),
    all_permissions=("reservations.manage_space_schedules",),
    scope_rule="reservation_office_scope",
)
ROUTE_POLICIES["space_administration_block_update"] = AuthorizationPolicy(
    key="space_administration_block_update",
    access="permission_protected",
    description="Move or relabel a maintenance or closure block.",
    methods=("POST",),
    route_names=("space_administration_block_update",),
    all_permissions=("reservations.manage_space_schedules",),
    scope_rule="reservation_office_scope",
)
ROUTE_POLICIES["space_administration_block_delete"] = AuthorizationPolicy(
    key="space_administration_block_delete",
    access="permission_protected",
    description="Remove a block and release the capacity it held.",
    methods=("POST",),
    route_names=("space_administration_block_delete",),
    all_permissions=("reservations.manage_space_schedules",),
    scope_rule="reservation_office_scope",
)
ROUTE_POLICIES["space_administration_booking_move"] = AuthorizationPolicy(
    key="space_administration_booking_move",
    access="permission_protected",
    description=(
        "Move a booking to another room. The destination is re-scoped against "
        "the actor's hierarchy independently of the source room."
    ),
    methods=("POST",),
    route_names=("space_administration_booking_move",),
    all_permissions=("reservations.manage_reservations",),
    scope_rule="reservation_office_scope",
)
ROUTE_POLICIES["space_administration_booking_cancel"] = AuthorizationPolicy(
    key="space_administration_booking_cancel",
    access="permission_protected",
    description="Cancel another user's booking with an audited reason.",
    methods=("POST",),
    route_names=("space_administration_booking_cancel",),
    all_permissions=("reservations.manage_reservations",),
    scope_rule="reservation_office_scope",
)


# --- unified self-service reservations -------------------------------------
ROUTE_POLICIES["my_reservations"] = AuthorizationPolicy(
    key="my_reservations",
    access="authenticated",
    description=(
        "Unified self-service reservation feed. Scoped to the signed-in user "
        "with no owner selector on the route, so there is nothing to tamper "
        "with; each source applies its own self-only queryset."
    ),
    methods=("GET",),
    route_names=("my_reservations",),
    scope_rule="self_only",
)
ROUTE_POLICIES["my_reservation_detail"] = AuthorizationPolicy(
    key="my_reservation_detail",
    access="authenticated",
    description="One of the reader's own reservations, resolved self-only.",
    methods=("GET",),
    route_names=("my_reservation_detail",),
    scope_rule="self_only",
)
ROUTE_POLICIES["my_reservation_cancel"] = AuthorizationPolicy(
    key="my_reservation_cancel",
    access="authenticated",
    description=(
        "Cancel one of the reader's own reservations. The unified layer only "
        "routes; the owning domain service re-checks permission, cutoff, and "
        "lifecycle before anything changes."
    ),
    methods=("POST",),
    route_names=("my_reservation_cancel",),
    scope_rule="self_only",
)

ROUTE_POLICIES["transaction_create"] = AuthorizationPolicy(
    key="transaction_create",
    access="permission_protected",
    description=("Guided transaction create, draft save, prepare, and people search."),
    methods=("GET", "POST"),
    route_names=(
        "transaction_new",
        "transaction_draft_save",
        "transaction_prepare",
        "transaction_people_search",
    ),
    any_permissions=(
        "web.manage_transactions",
        "web.create_own_transactions",
    ),
    scope_rule="user_office_scope",
)
ROUTE_POLICIES["transaction_workspace"] = AuthorizationPolicy(
    key="transaction_workspace",
    access="permission_protected",
    description="Sectioned transaction workspace; row scope re-checked in view.",
    methods=("GET",),
    route_names=("transaction_workspace",),
    any_permissions=(
        "web.view_transactions",
        "web.manage_transactions",
        "web.create_own_transactions",
        "web.view_own_transactions",
    ),
    scope_rule="user_office_scope",
)
ROUTE_POLICIES["transaction_workspace_write"] = AuthorizationPolicy(
    key="transaction_workspace_write",
    access="permission_protected",
    description="Mutate transaction workspace sections; row scope re-checked in view.",
    methods=("POST", "DELETE"),
    route_names=(
        "transaction_party_save",
        "transaction_party_end",
        "transaction_property_save",
        "transaction_key_date_save",
        "transaction_key_date_end",
        "transaction_note_save",
        "transaction_note_end",
        "transaction_assignment_save",
        "transaction_document_upload",
        "transaction_document_classify",
        "transaction_document_revision",
        "transaction_document_retire",
        "transaction_document_retry",
        "transaction_document_lock",
        "transaction_document_comment_save",
        "transaction_document_comment_resolve",
        "transaction_document_comment_end",
        "transaction_signature_package_create",
        "transaction_signature_package_save",
        "transaction_signature_package_send",
        "transaction_signature_package_cancel",
        "transaction_signature_signer_remind",
    ),
    any_permissions=(
        "web.manage_transactions",
        "web.create_own_transactions",
    ),
    scope_rule="user_office_scope",
)
ROUTE_POLICIES["transaction_document_file"] = AuthorizationPolicy(
    key="transaction_document_file",
    access="permission_protected",
    description=(
        "Authorized preview/download of transaction document versions; "
        "row scope re-checked in the delivery service."
    ),
    methods=("GET",),
    route_names=(
        "transaction_document_download",
        "transaction_document_preview",
    ),
    any_permissions=(
        "web.view_transactions",
        "web.manage_transactions",
        "web.create_own_transactions",
        "web.view_own_transactions",
    ),
    scope_rule="user_office_scope",
)
ROUTE_POLICIES["transaction_signature_ceremony"] = AuthorizationPolicy(
    key="transaction_signature_ceremony",
    access="authenticated",
    description=(
        "Hub-user ceremony for a transaction signature package. The view "
        "re-checks that the actor is the assigned signer."
    ),
    methods=("GET", "POST"),
    route_names=(
        "transaction_signature_ceremony",
        "transaction_signature_ceremony_complete",
        "transaction_signature_ceremony_decline",
    ),
    scope_rule="self_only",
)
ROUTE_POLICIES["transaction_signature_magic_link"] = AuthorizationPolicy(
    key="transaction_signature_magic_link",
    access="public",
    description=(
        "External magic-link ceremony. Token authenticity is enforced in the "
        "view; incomplete profiles are allowed."
    ),
    methods=("GET", "POST"),
    route_names=(
        "transaction_signature_magic_link",
        "transaction_signature_magic_link_complete",
        "transaction_signature_magic_link_decline",
    ),
    allow_incomplete_profile=True,
    auth_behavior="json",
)
ROUTE_POLICIES["transaction_signature_document_preview"] = AuthorizationPolicy(
    key="transaction_signature_document_preview",
    access="public",
    description=(
        "Preview a package document during ceremony. Hub auth or magic-link "
        "session is re-checked in the view."
    ),
    methods=("GET",),
    route_names=("transaction_signature_document_preview",),
    allow_incomplete_profile=True,
    auth_behavior="json",
)
ROUTE_POLICIES["transaction_signature_artifact_download"] = AuthorizationPolicy(
    key="transaction_signature_artifact_download",
    access="permission_protected",
    description=(
        "Download a sealed signed PDF or certificate of completion. Artifacts "
        "stay inside the Hub — an external signer is pointed at the brokerage "
        "rather than given a durable link to the executed agreement — and deal "
        "scope plus completed status are re-checked in the view."
    ),
    methods=("GET",),
    route_names=("transaction_signature_artifact_download",),
    any_permissions=(
        "web.view_transactions",
        "web.manage_transactions",
        "web.create_own_transactions",
        "web.view_own_transactions",
    ),
    scope_rule="user_office_scope",
)
ROUTE_POLICIES["my_transactions"] = AuthorizationPolicy(
    key="my_transactions",
    access="permission_protected",
    description="Agent-facing scoped transaction list.",
    methods=("GET",),
    route_names=("my_transactions",),
    any_permissions=(
        "web.view_transactions",
        "web.manage_transactions",
        "web.create_own_transactions",
        "web.view_own_transactions",
    ),
    scope_rule="user_office_scope",
)
