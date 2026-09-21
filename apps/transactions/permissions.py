"""Permission codenames owned by the transactions domain."""

from __future__ import annotations

# Scoped list/detail (also on web.OperationsPermission for ops nav).
VIEW_TRANSACTIONS = "web.view_transactions"

# Create drafts, edit non-status fields, and mutate assignments.
MANAGE_TRANSACTIONS = "web.manage_transactions"

# Agents may open a deal for themselves without the full manage grant.
CREATE_OWN_TRANSACTIONS = "web.create_own_transactions"

# Lifecycle transitions through the centralized service.
TRANSITION_TRANSACTIONS = "web.transition_transactions"

# Sensitive field projection — model permissions on Transaction.
VIEW_TRANSACTION_FINANCIALS = "transactions.view_transaction_financials"
VIEW_TRANSACTION_CLIENTS = "transactions.view_transaction_clients"
