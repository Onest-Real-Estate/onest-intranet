# oNEST Hub — issue tracker

Last refreshed: 2026-08-31

P0 platform work is complete. Remaining work is **41 open P1 feature issues** across inventory, reservations, training/docs/compliance, transactions, and CRM/MLS.

## Summary

| Status | Count |
| --- | ---: |
| Done (closed) | 61 |
| Remaining (open) | 41 |
| Open bugs | 0 |
| Open PRs | 0 |

---

## Live today

Everything else in the sidebar still shows **Coming soon**. Permissions exist; the feature flags in `apps/web/navigation.py` and `apps/web/operations.py` are still `False`.

### Agent nav (`HUB_FEATURES = True`)

- Dashboard
- Announcements
- My Contract
- My Office — Info & Resources
- Reports

### Admin nav (`OPERATIONS_FEATURES = True`)

- Users, New Agent List, Assign User Roles
- Offices, Office Resources
- Announcements, Contract Templates
- Operational Tasks, Feedback
- Quick Access

---

## Built but not flipped on in nav

Real views exist (direct URL works when authorized) but the nav still marks them unavailable. Per [docs/administrative-navigation.md](docs/administrative-navigation.md), flip the feature key to `True` in the same commit that replaces any placeholder.

| Feature key | Notes |
| --- | --- |
| `admin-agent-contracts` | Contract stack #48–#58 is closed |
| `admin-add-user` | Route exists; still a Soon stub in nav |

Platform Tasks (#96) closed as an internal module; `admin_platform_tasks` and `admin_it_support` still render sanitized placeholder pages.

---

## Done

### P0 — Platform foundation

- #3 SSO (Entra ID)
- #4 Agent onboarding
- #5–#7 Offices & org hierarchy
- #8–#13 Roles, permissions, scopes, frontend guards
- #14–#15 Audit logging & events
- #16–#20 App shell, nav, design system

### P1 — Profile & dashboard

- #31–#32 Agent profile (+ admin fields)
- #33–#39 Dashboard (metrics, Quick Access, My Day, Action Items)
- #77 Role-aware admin dashboards

### P1 — Announcements & office

- #40–#44 News & announcements
- #45–#47 Office info & resources

### P1 — Agent contracts

- #48–#54 Data model → templates → PDF → My Contract → one-click signing
- #55 Generate immutable signed contract PDF
- #56 Lifecycle statuses
- #57 Contract versioning and amendments
- #58 Contract notifications
- #49 Mentor/referral commission split

### P1 — Admin, notifications, platform

- #78–#81 User / onboarding / role / office admin
- #82–#83 Notifications (+ email prefs)
- #84 Quick Create
- #94 Global search
- #95 Feedback / support
- #96 Platform Tasks
- #97 Activity timelines
- #98 Operational reporting

### Other closed

- #1 Dual Representation on Transaction Type (enhancement / user request)
- #2 Separate Referral % and Mentor % (user request)

---

## Remaining

### Inventory (#59–#65)

| Issue | Title |
| ---: | --- |
| #59 | Office inventory data model |
| #60 | Admin inventory management |
| #61 | Agent Office Inventory browser |
| #62 | Reservation workflow |
| #63 | Prevent double booking |
| #64 | Reservation lifecycle |
| #65 | Overdue inventory notifications |

### Rooms & reservations (#66–#71)

| Issue | Title |
| ---: | --- |
| #66 | Room/space data model |
| #67 | Availability calendar |
| #68 | Room reservation workflow |
| #69 | Prevent overlapping reservations |
| #70 | Room administration |
| #71 | Unified My Reservations page |

### Training, documents, marketing, compliance (#85–#93)

| Issue | Title |
| ---: | --- |
| #85 | Training & Learning content library |
| #86 | Training administration & audience |
| #87 | Training progress, quizzes, live sessions |
| #88 | Documents & Forms library |
| #89 | Document/form version management |
| #90 | Marketing Resources |
| #91 | Policies & Compliance content library |
| #92 | Policy acknowledgement & tracking |
| #93 | Privacy-aware Agent Directory |

### Transactions (#99–#108)

| Issue | Title |
| ---: | --- |
| #99 | Transaction data model and lifecycle |
| #100 | Scoped transaction creation workflow |
| #101 | Transaction workspace, parties, property, key dates |
| #102 | Transaction document management and versioning |
| #103 | Transaction document e-signature workflow |
| #104 | Jurisdiction-aware checklist templates |
| #105 | Transaction tasks, deadlines, and reminders |
| #106 | Transaction compliance review workflow |
| #107 | Auditable transaction commission calculations |
| #108 | Transaction closure, activity, and notifications |

### CRM & MLS (#109–#117)

| Issue | Title |
| ---: | --- |
| #109 | CRM lead data model and pipeline lifecycle |
| #110 | CRM pipeline, lead workspace, activity timeline |
| #111 | Lead assignment, routing, claiming, reassignment |
| #112 | Buyer profiles and readiness workflow |
| #113 | Seller profiles and listing-readiness workflow |
| #114 | CRM follow-ups, appointments, transaction conversion |
| #115 | Safe Smart Plan automation |
| #116 | MLS integration foundation and compliance controls |
| #117 | Property search, alerts, saved properties, showing activity |

---

## Secondary gaps

Shipped features with follow-up work that is not tracked as separate GitHub issues.

| Area | Gap | Reference |
| --- | --- | --- |
| Global search | No providers yet for documents, training, transactions, CRM contacts, or policies | [docs/search.md](docs/search.md) |
| Notification delivery | Microsoft Graph and Slack are dormant stubs; email is the production push path | [docs/notifications.md](docs/notifications.md) |
| Agent nav placeholders | Transactions, My Reservations, Training, Documents, Marketing Resources, Policies, Office Inventory, and Agent Directory still route to `coming_soon` | `frontend/lib/hub-nav.ts` |

---

## Suggested next focus

### Quick wins

- Flip **Agent Contracts admin** to available in nav (code exists; flag + docs only)
- Start **inventory #59** (data model) — unblocks the rest of that module chain

### Build order by area

| Order | Area | Issues | Scope |
| ---: | --- | --- | --- |
| 1 | Operations | #59+ then #66+ | Inventory and room reservations (13 issues) |
| 2 | Content | #85–#92 | Training, documents, marketing, compliance (8 issues) |
| 3 | Transactions | #99–#108 | Full transaction stack (10 issues) |
| 4 | CRM & MLS | #109–#117 | Leads through property search (9 issues) |
| 5 | Agent Directory | #93 | Can ship after supporting domains exist |

Transactions and CRM are the largest remaining chunks (**19 issues combined**). Inventory/reservations is the next operational block before most agent-facing **My Office** tools go live.
