# Operational reporting

Scoped operational reports and secure exports live in `apps/web/reporting/`.
The framework mirrors the dashboard metric registry: selection is data,
selection is not protection, and effective access (not role labels) drives
entitlement.

## Surfaces

| Route | Name | Permission | Purpose |
| --- | --- | --- | --- |
| `GET /reports` | `report_catalog` | `web.view_reports` | Catalog of entitled reports |
| `GET /reports/<key>` | `report_detail` | `web.view_reports` + report perms | Interactive table/chart |
| `POST /reports/<key>/exports` | `report_export_create` | `web.view_reports` + `web.export_reports` | Queue export |
| `GET /reports/exports/<id>` | `report_export_status` | same | Poll progress/failure |
| `GET /reports/exports/<id>/download` | `report_export_download` | same | Protected stream |

Per-report calculators still require their own domain permissions (for example
`web.view_new_agents` for onboarding). Losing a domain grant removes the
report from the catalog and 403s a direct URL.

## Registry

`REPORT_DEFINITIONS` in `apps/web/reporting/registry.py` is an ordered tuple of
`ReportDefinition` rows. Each row carries:

| Field | Meaning |
| --- | --- |
| `key` | Stable camelCase identity |
| `columns` | Projected fields; export uses the same projection |
| `all_permissions` / `any_permission` | Capability gate |
| `scopes` | Supported breadths (`self`, `office`, `region`, `company`) |
| `filters` | Closed filter set preserved in typed URLs |
| `time_grain` | Declared grain (`day`…`year`, or `none`) |
| `calculation_version` | Bumped when inclusion/comparison rules change |
| `export_policy` | Formats, sync row limit, TTL, export permission |
| `definition` | Prose contract for status/date inclusion, timezone, currency, comparison |

`_validate_registry()` fails the process on duplicate keys, unknown scopes or
source modules, or missing definitions.

## Scope before aggregation

`run_report` resolves effective access, checks permissions and scope, then
calls the calculator. Calculators filter through
`scoped_users` / `new_agent_queryset` before totals or detail rows. Client
office keys intersect an already-scoped set; out-of-scope keys empty the
result without revealing whether the office exists.

## Aggregate reconciliation

Connected calculators (`onboardingProgress`, `officeHeadcount`) build
aggregates and chart series from the **same** filtered row set (via
`Counter` / per-office buckets). Drill-down rows therefore sum to the chart
and the reported total under the documented inclusion rules.

## Exports

- Interactive pages bound rows with `sync_row_limit` (default 500).
- Async exports calculate with `unbounded=True`, so the protected file is not
  capped by the interactive page bound.
- Larger or explicit exports create a `ReportExportJob` with an idempotency
  key (requestor + report + filters + format) inside a one-hour window.
- Jobs track `queued` → `running` → `ready` / `failed`, then expire after 24h.
- Files live in protected storage and are streamed only through
  `report_export_download` with `Cache-Control: private, no-store`. Expired
  jobs delete their file and answer 404.
- Snapshot metadata on the file and job includes requestor, scope, filters,
  generated time, data-as-of, and calculation version.
- Export columns never include fields hidden from the on-screen projection.

## Accessibility

Charts render decorative bars plus a required tabular equivalent. Zero series
and empty result sets use explicit status copy rather than silent blanks.

## Adding a report

1. Add a `ReportDefinition` (and a calculator if the source module is live).
2. Document inclusion, timezone, currency, and comparison in `definition`.
3. Grant any new permissions via catalog + roles + migration.
4. Cover selection, scope leakage, reconciliation, and export idempotency in
   `apps/web/tests/test_reporting.py`.
