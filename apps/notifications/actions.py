"""Reviewed allowlist of destinations a notification may offer.

A notification never stores a URL. It stores an action *key* from this module
plus the positional arguments of the Django route behind it, and the path is
reversed when the page is rendered. Three things follow from that:

* A producer cannot smuggle an off-site or ``javascript:`` destination into a
  reader's inbox — the key either exists here or the delivery is rejected.
* A route that is renamed or removed degrades to "no action" instead of a
  broken link, because :func:`resolve_action_href` fails closed.
* Following the action lands on a view with its own ``enforce_policy``, so a
  notification that outlived its grant cannot widen access at the destination.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import NoReverseMatch, reverse


@dataclass(frozen=True)
class NotificationAction:
    """One approved destination.

    ``arg_types`` mirrors the route's positional signature; anything else the
    producer supplies is rejected before the row is written.
    """

    key: str
    route_name: str
    label: str
    arg_types: tuple[type, ...] = ()


ACTION_DEFINITIONS: tuple[NotificationAction, ...] = (
    NotificationAction(
        key="open_onboarding_case",
        route_name="new_agent_onboarding",
        label="Open onboarding case",
        arg_types=(int,),
    ),
    NotificationAction(
        key="open_profile",
        route_name="profile",
        label="Open your profile",
    ),
    NotificationAction(
        key="open_dashboard",
        route_name="dashboard",
        label="Open your dashboard",
    ),
    NotificationAction(
        key="open_action_items",
        route_name="action_items_queue",
        label="Open action items",
    ),
    NotificationAction(
        key="open_user_directory",
        route_name="admin_users",
        label="Open the people directory",
    ),
    NotificationAction(
        key="open_agent_contract",
        route_name="agent_contract_workspace",
        label="Open contract",
        arg_types=(str,),
    ),
    NotificationAction(
        key="open_my_contract",
        route_name="my_contract",
        label="Open My Contract",
    ),
    NotificationAction(
        key="open_my_contract_sign",
        route_name="my_contract_sign",
        label="Sign your contract",
    ),
    NotificationAction(
        key="open_company_contract_sign",
        route_name="agent_contract_company_sign",
        label="Sign for the company",
        arg_types=(str,),
    ),
    NotificationAction(
        key="open_inventory_reservation",
        route_name="inventory_reservation_detail",
        label="Open reservation",
        arg_types=(str,),
    ),
    NotificationAction(
        key="open_admin_reservation",
        route_name="admin_reservation_detail",
        label="Open reservation",
        arg_types=(str,),
    ),
    NotificationAction(
        key="open_policy_detail",
        route_name="policy_detail",
        label="Open policy",
        arg_types=(int,),
    ),
)

ACTION_BY_KEY: dict[str, NotificationAction] = {
    action.key: action for action in ACTION_DEFINITIONS
}


class InvalidActionArguments(ValueError):
    """Producer arguments do not match the route's signature."""


def validate_action_args(key: str, args: tuple[str | int, ...]) -> tuple[object, ...]:
    """Coerce ``args`` to the route signature, or raise.

    Returns the coerced tuple so callers persist exactly what will later be
    reversed, rather than a string that happens to look like a number today.
    """
    action = ACTION_BY_KEY.get(key)
    if action is None:
        raise InvalidActionArguments(f"Unknown action: {key!r}")
    if len(args) != len(action.arg_types):
        raise InvalidActionArguments(
            f"Action {key!r} takes {len(action.arg_types)} argument(s), got {len(args)}"
        )
    coerced: list[object] = []
    for value, expected in zip(args, action.arg_types, strict=True):
        if expected is int:
            try:
                coerced.append(int(value))
            except (TypeError, ValueError) as exc:
                raise InvalidActionArguments(
                    f"Action {key!r} expects an integer argument"
                ) from exc
        else:
            coerced.append(str(value))
    return tuple(coerced)


def action_label(key: str) -> str:
    action = ACTION_BY_KEY.get(key)
    return action.label if action else ""


def resolve_action_href(key: str, args: list | tuple) -> str:
    """Reverse the action, or return ``""``.

    Fails closed on every unknown key, malformed argument list, and route that
    no longer reverses: a notification with no destination still reads fine,
    a notification pointing at a guessed path does not.
    """
    action = ACTION_BY_KEY.get(key)
    if action is None:
        return ""
    try:
        coerced = validate_action_args(key, tuple(args))
    except InvalidActionArguments:
        return ""
    try:
        return reverse(action.route_name, args=coerced)
    except NoReverseMatch:
        return ""
