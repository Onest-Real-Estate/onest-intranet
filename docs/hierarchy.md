# Organization hierarchy

The brokerage org tree is modeled as `Office` nodes:

`head_office` → `region` → `regional_office` → `branch`

Parent kind rules are enforced on `Office.clean()`. Cycles are rejected.
`region` is a denormalized pointer to the nearest region ancestor and is
refreshed on save and after `transfer_office`.

## Membership

`User.office` is the live primary workplace pointer. `UserOfficeMembership`
stores auditable primary/secondary history with effective dates. Hierarchy
membership never grants permissions by itself — effective access comes from
`UserRoleAssignment` plus the permission catalog.

## Restructuring

Only company-wide administrators may reparent offices (`transfer_office` in
`apps.user.services.hierarchy`). Product UI for hierarchy and active/assignable
status lives in [office-administration.md](office-administration.md) and requires
impact confirmation.

## Scope evaluation

`get_effective_access` yields `company_wide`, `region_keys`, and `office_keys`.
Query helpers such as `scope_queryset_for_offices` apply that tree before any
list or mutation. Inconsistent hierarchy fails closed at capability evaluation.
