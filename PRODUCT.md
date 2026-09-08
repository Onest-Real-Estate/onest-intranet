# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

oNEST real-estate agents use the Hub throughout the workday to complete
brokerage operations. Scoped office, branch, regional, and company
administrators manage the records within their delegated hierarchy.

## Product Purpose

oNEST HUB is the brokerage's internal operating system. It brings office
resources, reservations, transactions, compliance, training, and support into
one permission-aware workspace so staff can act without exposing records beyond
their role or office scope.

## Operating Context

The product is a dense desktop-first operational interface that must remain
fully usable on smaller screens. Users navigate with Microsoft SSO identities,
work in an assigned office and office timezone, and often need to scan or act
quickly between client-facing tasks.

## Capabilities and Constraints

- Django and Inertia own the server-rendered page protocol; React provides the
  interaction layer.
- Organizational scope and field-level privacy are enforced before data is
  serialized.
- Reservations are advisory in browse surfaces and authoritative only after an
  atomic server-side revalidation.
- Internal files use protected S3-compatible storage.
- URL-backed state must remain linkable and bounded.

## Brand Commitments

The product is named oNEST HUB. Its established voice is concise, calm, and
operational. `DESIGN.md` is the visual authority.

## Evidence on Hand

The repository contains the production data model, permission catalog,
organizational hierarchy, design system, and automated test suite. No customer
claims or marketing evidence should be invented.

## Product Principles

- Scope before serialization.
- Make the next valid action obvious.
- Preserve history and audit lifecycle changes.
- Keep advisory interfaces honest about authoritative server validation.
- Provide keyboard and assistive-technology parity for every workflow.

## Accessibility & Inclusion

Interactive workflows must support keyboard navigation, screen readers,
responsive layouts, visible focus, and useful loading, empty, error, and
disabled states. Dragging cannot be the only way to complete a task.
