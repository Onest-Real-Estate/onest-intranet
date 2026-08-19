# ONEST component system

The public components live in `frontend/components/design-system/` and are
exported from its `index.ts`. They are product-neutral: permission guards and
authorized data belong outside the component boundary.

## Public families

| Family | Public API | Supported states and composition |
| --- | --- | --- |
| Cards | `SurfaceCard`, header/content/footer/title/description, `PanelHeader`, `SurfaceCardMeta`, `CardStateMessage` | Default, interactive, loading, error, success, read-only |
| Tables | `DataTable<Row>`, `DataTableColumn<Row>`, `Pagination` | Sort, selection, pagination, overflow, loading, empty, error, `frame="bordered" \| "bare"` |
| Status badges | `StatusBadge`, `presentStatus` | Neutral, info, success, warning, destructive, safe unknown |
| Empty states | `EmptyState` | Compact/full, description and action slots |
| Dialogs | Dialog primitives, `DestructiveConfirmDialog` | Controlled/uncontrolled, Escape, overlay close, focus trap/restoration, loading confirmation |
| Forms | Field/label/description/error/summary/read-only components, `fieldA11yProps` | Required, optional, invalid, disabled through native controls, read-only, form-level errors |
| Uploaders | `FileUploader`, `UploadHandler`, `UploadedFile` | Drag/drop, keyboard choice, progress, client hint failure, server failure, retry, preview, removal, disabled, read-only |
| Page headers | `PageHeader` | Breadcrumb, eyebrow, description, metadata, responsive action slots |
| Metric cards | `MetricCard`, `MetricGroup` | Neutral, success, warning, destructive, trend, loading |
| Timelines | `Timeline`, `TimelineItem` | Dot or per-item `icon`, current step, semantic status tones |
| Filters | `FilterControls`, `FilterField` | Active count, reset, disabled reset, arbitrary control composition |
| Search controls | `SearchControl` | Controlled/uncontrolled, submit, clear, loading, disabled, error, `tone="outline" \| "subtle"`, `size` |

The catalog at `/design-system` demonstrates every family. Import from the
barrel only when several families are needed; high-use modules can import the
individual file so bundlers can eliminate unused code.

## Server contracts

### Validation

`apps.web.contracts.validation_errors()` returns:

```json
{
  "fields": { "field_name": ["One or more messages."] },
  "form": ["A form-level message."]
}
```

Field keys remain Django names because they match submitted HTML `name`
attributes. Components render messages as text. There is no unsafe HTML API.

### Lists

`apps.web.contracts.list_response()` returns `items`, `pagination`, `filters`,
and `sort`. Query state uses `q`, `page`, `pageSize`, `sort`, and `direction`;
feature-specific filters use stable explicit keys. `buildListUrl()` resets the
page when search, filtering, page size, or sorting changes.

### Status

The backend returns a status code, never a CSS class. Each feature owns an
explicit `Record<string, StatusPresentation>`. `presentStatus()` converts an
unknown value into the neutral “Unknown status” presentation.

### Uploads

`FileUploader` checks client hints for fast feedback. The upload endpoint must
revalidate file size, content, type, ownership, authorization, and storage
rules. A successful UI state only follows a successful endpoint response.

## Accessibility and responsive review

- Use semantic headings, forms, tables, lists, buttons, and links first.
- At 200% zoom, toolbars wrap and tables scroll inside their own region.
- Table sort buttons announce `aria-sort`; selection controls have row labels.
- Dialogs require a title and description. Radix traps focus and restores it;
  pass `fallbackFocusRef` when navigation may remove the trigger.
- Form summaries link to invalid controls and inline messages are announced.
- Statuses use words and icons in addition to color.
- Upload progress uses a named progressbar and errors use live status text.
- Global reduced-motion rules shorten nonessential animation to effectively
  zero while preserving state changes.

Manual review targets: keyboard-only use at 320 px and 200% zoom; VoiceOver or
NVDA spot checks for dialogs, form errors, table sorting/selection, upload
progress, and search clearing.

## Usage guidance

Do use the smallest component that owns the behavior, keep data/permissions in
the page, and supply action labels that name their target. Do not nest cards by
default, encode authorization through visibility, pass arbitrary backend
classes, or use color as the only state signal.

## Composition rules

- One panel heading per card, through `PanelHeader`. The right-hand slot takes
  either `meta` (a static fact) or `action` (a real control) — not both, and
  never a decorative icon tile.
- A `DataTable` inside a `SurfaceCard` uses `frame="bare"`. The card already
  draws the frame; two nested borders read as a bug.
- `SearchControl` defaults to `tone="outline"`. Use `tone="subtle"` only where
  the field sits among other chrome, such as the application header.
- `Timeline` defaults to a dot marker. `icon` is opt-in per item and should
  carry meaning, not decoration.

## Migration notes

Changes made while the system was adopted by the shell and the dashboard:

- `PanelHeader` and `SurfaceCardMeta` are additive. Existing
  `SurfaceCardHeader` + `SurfaceCardTitle` composition still works; new panels
  should prefer `PanelHeader`.
- `DataTable` gained `frame`, defaulting to `bordered` — existing call sites are
  unaffected.
- `SearchControl` gained `tone` and `size`, defaulting to the previous
  appearance.
- `MetricCard` now carries its own `bg-card` border and radius, so it renders
  correctly outside a `MetricGroup`. Consumers that supplied those classes
  themselves can drop them.
- `PageHeader` title type is now `clamp(1.5rem, 2.4vw, 1.875rem)` semibold,
  down from `clamp(1.75rem, 3vw, 2.25rem)` bold. No API change.
- `Timeline` markers are dots rather than a check on every item; pass `icon` to
  restore a per-item mark.

## Ownership and changes

The frontend maintainers own tokens and public APIs; backend maintainers own
validation, list, status-code, and upload endpoint contracts. Additive props are
preferred. A removal, rename, default change, or semantic behavior change needs
a migration note here, catalog updates, consumer updates, and tests in the same
change. Generated shadcn primitives under `frontend/components/ui/` are not the
public ONEST API and must be regenerated rather than hand-edited.
