"""Permission codenames owned by the contract domain."""

from __future__ import annotations

# Metadata / standing for people in scope (also declared on web.OperationsPermission
# so existing nav and directory gates keep working).
VIEW_AGENT_CONTRACTS = "web.view_agent_contracts"

# Create and edit drafts within scope. Lifecycle transitions will reuse this
# grant until a finer split ships with the state machine.
MANAGE_AGENT_CONTRACTS = "contract.manage_agent_contracts"
MANAGE_CONTRACT_TEMPLATES = "contract.manage_contract_templates"
APPROVE_CONTRACT_TEMPLATES = "contract.approve_contract_templates"

# Commercial terms: agent/office split, mentor, referral, fees, caps.
VIEW_COMMISSION_TERMS = "contract.view_commission_terms"

# Restricted broker notes — never implied by metadata or commission grants.
VIEW_INTERNAL_NOTES = "contract.view_internal_notes"

# Recipient may read their own commercial terms on My Contract surfaces.
VIEW_OWN_COMMISSION = "web.view_own_commission"
