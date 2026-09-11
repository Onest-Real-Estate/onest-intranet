"""Awaiting-signature dashboard widget.

A window on the agent-contract queue at `admin_agent_contracts`.
`scoped_contract_queryset` is that page's own visibility gate — it requires
`web.view_agent_contracts` and applies the administration scope — so the panel
can never name a contract the queue would have withheld.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils import timezone

from apps.contract.models import AgentContract
from apps.contract.services import scoped_contract_queryset
from apps.contract.statuses import STATUS_TONES, ContractStatus
from apps.web.dashboard.envelope import ProviderResult, empty, ready
from apps.web.dashboard.providers import DashboardContext

_MAX_ROWS = 5

#: Issued and with the agent, waiting on their signature. `DRAFT` and
#: `READY_FOR_REVIEW` are still the brokerage's own work and belong to whoever
#: is drafting, not to a queue titled "awaiting signature".
_AWAITING = (ContractStatus.SENT, ContractStatus.VIEWED)


def _waiting_label(contract: AgentContract, *, now) -> str:
    sent = contract.sent_at or contract.updated_at
    if sent is None:
        return "Awaiting signature"
    days = (now - sent).days
    if days <= 0:
        return "Sent today"
    if days == 1:
        return "Waiting 1 day"
    return f"Waiting {days} days"


def contracts_awaiting_signature(context: DashboardContext) -> ProviderResult:
    """Issued contracts sitting with the agent, oldest first."""
    queryset = scoped_contract_queryset(context.user).filter(status__in=_AWAITING)
    total = queryset.count()
    if total == 0:
        return empty(
            "Nothing awaiting signature",
            "Contracts sent to an agent appear here until they sign.",
            action_label="Open agent contracts",
            action_href=reverse("admin_agent_contracts"),
        )

    now = context.now or timezone.now()
    rows = []
    for contract in queryset.order_by("sent_at", "pk")[:_MAX_ROWS]:
        recipient = contract.recipient
        rows.append(
            {
                "id": str(contract.public_id),
                "title": recipient.get_full_name() or recipient.email,
                "subtitle": (
                    contract.office.name if contract.office_id else "No office"
                ),
                "meta": _waiting_label(contract, now=now),
                # `ContractStatus` is a `TextChoices`, so the label is on the
                # enum. Django's generated `get_status_display` is invisible to
                # the type checker and says the same thing.
                "badge": str(ContractStatus(contract.status).label),
                "tone": STATUS_TONES.get(contract.status, "neutral"),
                "href": reverse(
                    "agent_contract_workspace", args=[str(contract.public_id)]
                ),
            }
        )

    return ready(
        {
            "total": total,
            "rows": rows,
            "viewAllHref": reverse("admin_agent_contracts"),
        }
    )
