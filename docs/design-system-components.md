# ONEST component system

The public components live in `frontend/components/design-system/` and are
exported from its `index.ts`. They are product-neutral: permission guards and
authorized data belong outside the component boundary.

## Public families

| Family | Public API | Supported states and composition |
| --- | --- | --- |
| Cards | `SurfaceCard`, header/content/footer/title/description, `PanelHeader`, `SurfaceCardMeta`, `CardStateMessage` | Default, interactive, loading, error, success, read-only, `PanelHeader divided` |
| Tables | `DataTable<Row>`, `DataTableColumn<Row>`, `Pagination` | Sort, selection, pagination, overflow, loading, empty, error, `frame="bordered" \| "bare" \| "bleed"` |
| Status badges | `StatusBadge`, `presentStatus` | Neutral, info, success, warning, destructive, safe unknown |
| Empty states | `EmptyState` | Compact/full, description and action slots |
| Dialogs | Dialog primitives, `DestructiveConfirmDialog` | Controlled/uncontrolled, Escape, overlay close, focus trap/restoration, loading confirmation |
| Forms | Field/label/description/error/summary/read-only components, `FormActionBar`, `DateField` / `DatePicker`, `fieldA11yProps` | Required, optional, invalid, disabled through native controls, read-only, form-level errors, calendar date (and optional time) without the browser date picker |
| Uploaders | `FileUploader`, `UploadHandler`, `UploadedFile` | Drag/drop, keyboard choice, progress, client hint failure, server failure, retry, preview, removal, disabled, read-only |
| Page headers | `PageHeader` | Breadcrumb, eyebrow, description, metadata, responsive action slots |
| Metric cards | `MetricCard`, `MetricGroup` | Neutral, success, warning, destructive, trend, loading |
| Timelines | `Timeline`, `TimelineItem` | Dot or per-item `icon`, current step, semantic status tones |
| Filters | `FilterControls`, `FilterField` | Active count, reset, disabled reset, arbitrary control composition |
| Search controls | `SearchControl` | Controlled/uncontrolled, submit, clear, loading, disabled, error, `tone="outline" \| "subtle"`, `size` |
| Hierarchy | `HierarchyBreadcrumb`, `HierarchySelector` | Org path breadcrumbs with inactive badges; searchable grouped office picker for large trees |
| Roles | `RoleBadge` | Stable-code role chip with optional scope; presentation only — never authorization |

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
- `DateField` and `DatePicker` are the date controls. Do not use
  `<input type="date">` or `datetime-local`; those render the OS picker.
  Posted values stay ISO (`yyyy-MM-dd`, or `yyyy-MM-ddTHH:mm` when
  `includeTime` is set).
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
- A `DataTable` inside a `SurfaceCard` uses `frame="bleed"`. The card already
  draws the frame, so two nested borders read as a bug; `bleed` additionally
  runs the row rules to both card edges and hands the card's 20px inset back to
  the outer columns, so the first column's left edge lands on the panel heading.
  `frame="bare"` remains for a table that should stay inside the card padding.
- `PanelHeader divided` rules the header off from the body. Earn it when the
  body is a form or a table; leave it off when the body is prose or a short
  list, where the spacing already separates them.
- A long form closes with `FormActionBar` — a recessed bar carrying the save
  status and the submit control. It is deliberately not another `SurfaceCard`:
  giving the closing action the same white surface as the field panels above it
  makes it read as one more group to fill in.
- Column visibility inside a panel belongs to container queries (`@container`
  plus `@md:`/`@2xl:`), not viewport breakpoints. A table in a 736px column has
  no idea that the *window* is 1280px wide, and `xl:table-cell` there reveals
  columns the panel cannot fit.
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

Changes made while the four core screens were brought onto one spacing system:

- `PanelHeader` gained `divided` (default `false`) — additive. Pages that spelled
  the rule out as `className="border-border/60 border-b pb-5"` should drop it.
- `DataTable` gained `frame="bleed"` — additive; `bordered` and `bare` are
  unchanged. Call sites that hand-rolled the bleed with
  `-mx-5 border-y [&_td]:px-2 …` should drop those classes.
- `FormActionBar` is new. It replaces the hand-rolled save bars on the profile
  and user-administration forms, which had drifted to different tints and radii.
- `SelectField` (in `components/profile/`) gained `className`, applied to the
  field wrapper so a field can span grid columns. `controlClassName` still
  targets only the trigger.

## Ownership and changes

The frontend maintainers own tokens and public APIs; backend maintainers own
validation, list, status-code, and upload endpoint contracts. Additive props are
preferred. A removal, rename, default change, or semantic behavior change needs
a migration note here, catalog updates, consumer updates, and tests in the same
change. Generated shadcn primitives under `frontend/components/ui/` are not the
public ONEST API and must be regenerated rather than hand-edited.
