# Onest intranet design system

Component APIs, state coverage, accessibility expectations, and change policy are
documented in [`design-system-components.md`](design-system-components.md). The
authenticated living catalog is available at `/design-system`.

This system translates the gold house-and-key logo into an accessible, practical interface for daily internal use. The approved oNEST gold, `#DDB52A`, is the signature color; semantic UI tokens use contrast-adjusted variants where needed.

## Principles

1. **Clear before decorative.** Dense operational information should remain easy to scan.
2. **Warm and trustworthy.** Gold and warm neutrals distinguish Onest without making every surface feel promotional.
3. **Accessible by default.** Never rely on color alone; pair status color with text or an icon and preserve visible keyboard focus.
4. **Consistent over custom.** Product work should use semantic shadcn tokens, not one-off hex values.

## Color

| Role | Light reference | Use |
| --- | --- | --- |
| Brand gold | `#DDB52A` | Logo, small highlights, decorative details |
| Primary | `oklch(0.50 0.115 74)` | Primary actions, active navigation, links |
| Background | `oklch(0.985 0.006 80)` | App canvas |
| Foreground | `oklch(0.22 0.018 72)` | Main text |
| Card | `#FFFFFF` | Raised content surfaces |
| Muted | `oklch(0.96 0.008 78)` | Secondary surfaces and table headers |
| Destructive | `oklch(0.56 0.20 27)` | Errors and irreversible actions |
| Success | `oklch(0.49 0.12 150)` | Completed and healthy states |
| Warning | `oklch(0.68 0.14 70)` | Attention-needed *surfaces* (badges, banners) |
| Warning ink | `oklch(0.45 0.115 68)` | Attention-needed **text** (`text-warning-ink`) |
| Info | `oklch(0.52 0.13 245)` | Neutral notices and guidance |

Use `bg-primary`, `text-muted-foreground`, `border-border`, and the other semantic utilities exposed in `frontend/css/app.css`. Use `brand-text`, `brand-surface`, `brand-well` (tinted icon well), and `brand-action` (the signature gold call to action, as on sign-in) only for brand expression—not general UI state. The `.dark` class switches the complete token set, including charts and sidebar colors.

`--warning` is a surface tint: as text on a card it only reaches about 2.4:1. Status **copy** uses `text-warning-ink`, which is the same hue darkened to a readable step. The same distinction applies in reverse to `--warning-foreground`, which is the ink that sits *on* a warning surface and renders near-black anywhere else.

## Typography

The preferred UI face is **Plus Jakarta Sans** (self-hosted variable cut), falling back to the platform sans-serif. Headings use 600–700 weight with tight tracking; labels use 600 with slightly open tracking, matching `DESIGN.md`.

| Style | Tailwind recipe | Typical use |
| --- | --- | --- |
| Display | `text-[40px] font-bold leading-12 tracking-[-0.02em]` | Rare hero copy |
| Page title | `text-[clamp(1.5rem,2.4vw,1.875rem)] font-semibold tracking-[-0.02em]` | One per page, via `PageHeader` |
| Section title | `text-base font-semibold tracking-[-0.01em]` | Page sections and panel headings |
| Card title | `font-semibold leading-none` | Nested card headings |
| Body | `text-sm` or `text-base leading-6` | Interface and long-form copy |
| Supporting | `text-sm text-muted-foreground` | Descriptions and metadata |
| Label | `text-xs font-semibold tracking-[0.02em]` | Form and data labels |

Use sentence case. Reserve all caps for the compact ONEST wordmark. Keep paragraphs near 65 characters per line when possible.

## Spacing and layout

Use Tailwind's 4 px spacing scale. The default gaps are 8 px for tightly related controls, 16 px for component content, 24 px between sections, and 40–64 px for page-level separation. The dashboard is the reference implementation: 40 px between bands, 24 px within a band, 12 px between a section heading and its content — the contrast between those intervals is what creates rhythm. Use the shared `page-shell` utility for application pages; it provides a `max-w-6xl` centered container and responsive gutters. A single-column form page sets its own narrower width instead, so the page header stays aligned with the form it introduces rather than floating out at the gutter (see `pages/Profile.tsx`).

The workspace panel is flush: it runs to the top and right edges of the window with no margin, radius, or shadow of its own. The sidebar's right border is the only seam between navigation and content — a floating, rounded content card wastes edge space and reads as a demo rather than an application.

Forms should be one column by default. Data-heavy views can expand to a responsive grid, but related labels and values should stay visually grouped.

## Shape and elevation

- Base radius: 12 px (`--radius: 0.75rem`). Buttons and inputs use the derived medium radius; cards use large or extra-large radii.
- Borders establish structure. Shadows should communicate elevation, not decorate every container.
- Use `shadow-sm` for ordinary cards and popovers. Reserve larger soft shadows for focused flows such as sign-in.

## Components and interaction

- **Buttons:** one primary action per region. Use `secondary` for a safe alternative, `outline` for lower-emphasis actions, `ghost` in navigation/toolbars, and `destructive` only for destructive work.
- **Forms:** labels remain visible above fields. Place validation messages directly below the field with `text-destructive`. Do not use placeholder text as a label.
- **Cards:** group one concept or task. Avoid nesting cards unless hierarchy would otherwise be ambiguous.
- **Badges:** use for short states or categories, not sentences. Pair semantic colors with explicit words such as “Approved” or “Overdue.”
- **Tables:** right-align numbers, keep headers concise, and use a muted header surface. Column headers render as 12 px micro-caps (`uppercase`, `tracking-[0.06em]`) so they read as labels rather than a first row of data. A table inside a card uses `frame="bare"` — one frame, not two. On narrow screens, prioritize or stack columns rather than shrinking text below 14 px.
- **Navigation:** keep the primary nav stable. The active item uses the sidebar accent surface, semibold type, a `text-primary` icon, and the gold left rail, and it also exposes `aria-current="page"`. Sidebar sections are declared in `HUB_NAV_GROUPS`; the uppercase group label is the only separation — no rules between groups. Sections without a backend show a derived "Soon" marker (`isComingSoon`) as plain muted type, never a pill: a rail of a dozen chips reads as a mockup rather than a product.
- **Icon tiles:** one tile vocabulary via `IconWell`. `tone="brand"` (gold) marks a small, countable set of brand moments — the quick-access launchers, the empty-state mark. `tone="muted"` is available for a one-off neutral tile. Panel headings carry **no** tile: the heading identifies the panel, and a tile repeated beside every title on a page competes with the data underneath it.
- **Panel headers:** use `PanelHeader` — heading, optional description, and at most one right-hand slot: `meta` for a static fact or `action` for a real control. Static facts render through `SurfaceCardMeta` as plain muted type, never a pill or a chevron, so they cannot pose as a dropdown.
- **Badges:** `warning` uses `text-warning-ink` over the tint, never `--warning-foreground` — that token is the ink for a *solid* warning surface and disappears on a dark card.
- **Timelines:** the default marker is a toned dot; `current` widens its ring. Pass `icon` only where the mark means something — a check on a step that is genuinely complete. A check on every entry claims progress the data does not support.
- **Interactive cards and rows:** one response — border tint, a one-pixel lift, a shadow step, trailing icon to full ink, 150 ms. Focus rings carry `ring-offset-2`.
- **Arrival motion:** deferred content uses the `.arrive` utility (240 ms rise + fade). Use an animation, never a transition from a hidden default, so content stays visible if it never runs.

All interactive controls need a visible focus ring, a minimum practical target of 36 px (44 px on touch-heavy screens), a disabled state, and clear hover/pressed feedback. Animations should generally stay between 120–200 ms; `app.css` carries a global `prefers-reduced-motion` override so individual components do not have to repeat it.

A control whose backend does not exist yet says so rather than doing nothing: mark it `aria-disabled` with a tooltip naming what is missing (see `PendingAction` in `HubLayout`), or point it at the `coming_soon` section that will own it.

## Icons and imagery

Use Lucide icons at 16–20 px with a consistent 1.5 px stroke (`LucideProvider` in `frontend/main.tsx`). Active icons are deep charcoal; inactive or decorative icons use muted text. Pair icons with labels; they do not replace uncommon action labels. Use the compact `BrandMark` component in product chrome and the supplied full logo only in brand/marketing contexts where its detail remains legible.

## Implementation checklist

- Choose semantic tokens rather than raw palette values.
- Give each page a `<Head title>`, one `h1`, and heading elements for widget titles (`<CardTitle asChild><h2>…`).
- Check light and `.dark` themes.
- Check keyboard focus and logical tab order.
- Verify empty, loading, error, disabled, and success states.
- Test at 320 px, 768 px, and a desktop width.
- Confirm text/background contrast and never encode status with color alone.
