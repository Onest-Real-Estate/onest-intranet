"""The workspace sidebar must offer every move the server will authorize.

``allowed_actions`` is a presentation adapter, and the React page used to
restate its codes by hand in a run of ``allowedActions.includes(...)`` checks.
That list drifted: ``mark_viewed``, ``mark_signed``, and ``expire`` were
authorized and had no button, so a manager could not advance a contract past
``sent`` — the only visible moves there were supersede and terminate.

These tests read the real sources rather than a copy of them. The action codes
come from ``allowed_actions`` itself, exercised across every status, and the
buttons come from the frontend registry file. Neither side can add a code
without the other noticing.

No database: ``allowed_actions`` reads only ``status`` and ``recipient_id`` off
the contract, and a superuser short-circuits the permission lookup.
"""

from __future__ import annotations

import re
from pathlib import Path

from apps.contract.lifecycle import CONFIRM_REQUIRED, allowed_actions
from apps.contract.models import AgentContract
from apps.contract.statuses import ContractStatus
from apps.contract.views import agent_contract_views
from apps.user.models import User

REGISTRY = (
    Path(__file__).resolve().parents[3]
    / "frontend/components/administration/contract-lifecycle.ts"
)


def _block(source: str, declaration: str, close: str = "\n};") -> str:
    """The text between ``declaration`` and the line that closes its literal."""
    start = source.index(declaration)
    rest = source[start + len(declaration) :]
    return rest[: rest.index(close)]


def _keys(block: str) -> set[str]:
    return set(re.findall(r"^  ([a-z_]+): \{", block, flags=re.MULTILINE))


def _registry() -> str:
    assert REGISTRY.exists(), f"Lifecycle registry moved: {REGISTRY}"
    return REGISTRY.read_text()


def registry_action_codes() -> set[str]:
    return _keys(_block(_registry(), "export const LIFECYCLE_ACTIONS"))


def registry_confirm_codes() -> set[str]:
    return _keys(_block(_registry(), "export const CONFIRM_LIFECYCLE"))


def offerable_actions() -> set[str]:
    """Every code ``allowed_actions`` can return, across every status."""
    actor = User(pk=1, is_superuser=True)
    codes: set[str] = set()
    for status in ContractStatus.values:
        codes.update(allowed_actions(actor, AgentContract(status=status)))
    return codes


def test_every_offerable_action_has_a_button():
    offerable = offerable_actions()

    assert offerable, "allowed_actions returned nothing for a superuser"
    missing = sorted(offerable - registry_action_codes())
    assert not missing, (
        f"The workspace has no button for {missing}. Add them to "
        "LIFECYCLE_ACTIONS in frontend/components/administration/"
        "contract-lifecycle.ts, or stop offering them from allowed_actions."
    )


def test_the_registry_does_not_invent_actions():
    """A button for a code the server never offers is dead UI."""
    extra = sorted(registry_action_codes() - offerable_actions())

    assert not extra, (
        f"LIFECYCLE_ACTIONS declares {extra}, which allowed_actions never "
        "returns for any status."
    )


def test_the_registry_orders_every_action_it_declares():
    """``LIFECYCLE_ACTION_ORDER`` decides which move is the gold one."""
    source = _registry()
    ordered = set(
        re.findall(
            r'"([a-z_]+)"',
            _block(
                source,
                "export const LIFECYCLE_ACTION_ORDER: LifecycleActionCode[]",
                close="\n];",
            ),
        )
    )

    assert ordered == registry_action_codes()


def test_confirm_required_moves_all_carry_dialog_copy():
    """A move the server refuses without ``confirmed`` needs a dialog."""
    missing = sorted(set(CONFIRM_REQUIRED) - registry_confirm_codes())

    assert not missing, (
        f"{missing} require confirmation server-side but have no entry in "
        "CONFIRM_LIFECYCLE, so the button would post unconfirmed and fail."
    )


def test_every_offerable_action_has_a_success_message():
    """Otherwise the flash falls back to 'Lifecycle update saved'."""
    source = Path(agent_contract_views.__file__).read_text()
    labelled = set(
        re.findall(r'"([a-z_]+)":', _block(source, "    labels = {", close="\n    }"))
    )

    missing = sorted(offerable_actions() - labelled)
    assert not missing, f"No flash message for {missing} in agent_contract_lifecycle."
