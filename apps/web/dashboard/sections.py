"""Agent-facing hub sections.

Kept apart from the widget registry so ``web.navigation`` can import the
section map without pulling in providers, the ORM, or the metric registry.
"""

from __future__ import annotations

HUB_SECTIONS: dict[str, str] = {
    "announcements": "Announcements",
    "my-contract": "My contract",
    "my-tools": "My tools",
    "agent-transactions": "Agent transactions",
    "my-reservations": "My reservations",
    "office-info": "Office info",
    "office-resources": "Office resources",
    "office-inventory": "Office inventory",
    "room-availability": "Room availability",
    "training-learning": "Training & learning",
    "documents-forms": "Documents & forms",
    "marketing-resources": "Marketing resources",
    "policies-compliance": "Policies & compliance",
    "agent-directory": "Agent directory",
}


#: Sections whose live destination has shipped, mapped to the route that serves
#: it.
#:
#: A section stays in ``HUB_SECTIONS`` for good — the key is what the navigation
#: registry and Quick Access hang on — so the Coming Soon stub at
#: ``/hub/<section>`` outlives the placeholder it was written for. Without this
#: map an old bookmark or a link somebody pasted into chat before the feature
#: shipped keeps answering "not built yet" about a page that has been live for
#: months. Listed sections redirect to the real thing instead.
#:
#: Every entry here must have ``HUB_FEATURES[section] is True``; a test pins
#: that, so flipping the flag without adding the route (or the reverse) fails.
LIVE_SECTION_ROUTES: dict[str, str] = {
    "announcements": "announcements",
    "my-contract": "my_contract",
    "my-tools": "my_tools",
    "my-reservations": "my_reservations",
    "office-info": "office_info",
    "office-resources": "office_resources",
    "office-inventory": "office_inventory",
    "room-availability": "room_availability",
    "training-learning": "training_learning",
    "marketing-resources": "marketing_resources",
    "policies-compliance": "policies_compliance",
    "agent-directory": "agent_directory",
}
