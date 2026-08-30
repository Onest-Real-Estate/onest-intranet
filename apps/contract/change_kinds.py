"""Stable contract family change kinds (amendment vs replacement).

``AgentContract.change_kind`` records *why* a family version exists. Status and
lifecycle still live in :mod:`apps.contract.statuses` /
:mod:`apps.contract.lifecycle`; this module only names the relationship role.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class ContractChangeKind(models.TextChoices):
    ORIGINAL = "original", _("Original agreement")
    AMENDMENT = "amendment", _("Amendment")
    ADDENDUM = "addendum", _("Addendum")
    REPLACEMENT = "replacement", _("Replacement")


#: Drafts created through the amendment workflow.
AMENDMENT_KINDS = frozenset({ContractChangeKind.AMENDMENT, ContractChangeKind.ADDENDUM})

#: Drafts that fully replace a prior governing version when activated.
REPLACEMENT_KINDS = frozenset({ContractChangeKind.REPLACEMENT})


def change_kind_label(code: str) -> str:
    try:
        return str(ContractChangeKind(code).label)
    except ValueError:
        return code
