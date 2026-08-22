"""Agent-facing hub sections.

Kept apart from the widget registry so ``web.navigation`` can import the
section map without pulling in providers, the ORM, or the metric registry.
"""

from __future__ import annotations

HUB_SECTIONS: dict[str, str] = {
    "announcements": "Announcements",
    "my-contract": "My contract",
    "agent-transactions": "Agent transactions",
    "my-reservations": "My reservations",
    "office-info": "Office info",
    "office-resources": "Office resources",
    "office-inventory": "Office inventory",
    "training-learning": "Training & learning",
    "documents-forms": "Documents & forms",
    "marketing-resources": "Marketing resources",
    "policies-compliance": "Policies & compliance",
    "agent-directory": "Agent directory",
}
