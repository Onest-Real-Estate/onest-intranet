# Onest intranet design system

Component APIs, state coverage, accessibility expectations, and change policy are
documented in [`design-system-components.md`](design-system-components.md). The
authenticated living catalog is available at `/design-system`.

**Precedence.** This file is the **component contract**: how each component
behaves, what states it covers, and the rules product work has to follow.
[`DESIGN.md`](../DESIGN.md) at the repository root is the **token and
visual-world source of truth**: what the colour, type, shape, and depth values
*are*. When the two disagree about a value, `DESIGN.md` wins; when they disagree
about a component's behaviour, this file wins. Neither may contradict
`frontend/css/app.css`, which is what actually ships.

This system translates the gold house-and-key logo into an accessible, practical interface for daily internal use. The approved oNEST gold, `#DDB52A`, is the signature color; semantic UI tokens use contrast-adjusted variants where needed.

## Principles

1. **Clear before decorative.** Dense operational information should remain easy to scan.
2. **Neutral field, rationed gold.** The greys are genuinely neutral so the one gold thing on a screen — the primary action — carries the whole brand. Gold is secondary in area and primary in meaning.
3. **Accessible by default.** Never rely on color alone; pair status color with text or an icon and preserve visible keyboard focus.
4. **Consistent over custom.** Product work should use semantic shadcn tokens, not one-off hex values.

## Color

| Role | Light reference | Use |
| --- | --- | --- |
| Brand gold | `#DDB52A` | The one primary action per region, the logo, the active nav icon, the focus ring |
| Primary | `oklch(0.50 0.115 74)` | Primary actions, active navigation, links |
| Background | `oklch(1 0 0)` | App canvas — white, the same value as a card |
| Foreground | `oklch(0.21 0.003 286)` | Main text |
| Card | `oklch(1 0 0)` | Panels. Separated from the canvas by their border, not by a tonal step |
| Muted | `oklch(0.968 0.002 286)` | The one tonal step: table header bands, wells, read-only panels |
| Muted foreground | `oklch(0.51 0.005 286)` | Descriptions, metadata, inactive icons. 5.75:1 on white |
| Border | `oklch(0.917 0.003 286)` | The hairline that carries all structure |
| Destructive | `oklch(0.56 0.20 27)` | Errors and irreversible actions |
| Success | `oklch(0.49 0.12 150)` | Completed and healthy states |
| Warning | `oklch(0.68 0.14 70)` | Attention-needed *surfaces* (badges, banners) |
| Warning ink | `oklch(0.45 0.115 68)` | Attention-needed **text** (`text-warning-ink`) |
| Info | `oklch(0.52 0.13 245)` | Neutral notices and guidance |

Use `bg-primary`, `text-muted-foreground`, `border-border`, and the other semantic utilities exposed in `frontend/css/app.css`. Use `brand-text`, `brand-surface`, `brand-well` (tinted icon well), and `brand-action` (the signature gold call to action, as on sign-in) only for brand expression—not general UI state. The `.dark` class switches the complete token set, including charts and sidebar colors. That class is written by exactly two places: the pre-paint script in `templates/layout.html`, which resolves the reader's stored choice or their operating system before the first frame, and `frontend/lib/theme.ts`, which owns it afterwards. Toggling it from a component is a bug — the theme would flash on every load. The reader's control lives in the sidebar footer and cycles system → light → dark.

Neutrals stay under 0.006 chroma. An earlier revision tilted every grey toward the brand hue 72–80; at one panel that reads as warmth, across a page of them it reads as a yellow cast on white paper, and it competes with the only colour on the screen that is supposed to mean something. Warmth is gold's job, and gold is rationed to one button.

`--warning` is a surface tint: as text on a card it only reaches about 2.4:1. Status **copy** uses `text-warning-ink`, which is the same hue darkened to a readable step. The same distinction applies in reverse to `--warning-foreground`, which is the ink that sits *on* a warning surface and renders near-black anywhere else.

## Typography

The preferred UI face is **Plus Jakarta Sans** (self-hosted variable cut), falling back to the platform sans-serif. Headings use 600–700 weight with tight tracking; labels use 600 with slightly open tracking, matching `DESIGN.md`.

| Style | Tailwind recipe | Typical use |
| --- | --- | --- |
| Display | `text-[40px] font-bold leading-12 tracking-[-0.02em]` | Rare hero copy |
| Page title | `text-2xl leading-8 font-bold tracking-[-0.02em]` | One per page, via `PageHeader`. Fixed, never a viewport clamp |
| Section title | `text-base leading-6 font-semibold tracking-[-0.01em]` | Page sections and panel headings (`PanelHeader`) |
| Card title | `font-semibold leading-none` | Nested card headings |
| Body | `text-sm` or `text-base leading-6` | Interface and long-form copy |
| Supporting | `text-sm text-muted-foreground` | Descriptions and metadata |
| Label | `text-xs font-semibold tracking-[0.02em]` | Form and data labels |
| Micro label | `text-micro` (11 px) | Chrome only: sidebar group labels, breadcrumbs, keycaps, counters |
| Metric figure | `text-metric font-bold tracking-[-0.02em] tabular-nums` | Stat figures, via `MetricCard` |
| Metric label | `text-xs font-semibold tracking-[0.06em] uppercase` | The label over a figure — literally the same recipe as a table column header |

Use sentence case. Reserve all caps for the compact ONEST wordmark. Cap prose with `max-w-measure` (34 rem ≈ 70 characters at the 14 px body step) rather than restating a `max-w-2xl`/`max-w-3xl` guess per page. The cap belongs on the paragraph, not on the column that holds it — a description should stop before its container does.

`text-micro` is the one step below `text-xs`, and it is a **chrome** step: labels that name a region, keyboard hints, and counters — never content a reader has to read. It exists so the shell stops accumulating a private ramp of 10 px/11 px near-duplicates. There is no step below it; a literal `text-[10px]` is a bug.

## Spacing and layout

Use Tailwind's 4 px spacing scale. Every application page uses the same ladder, and the contrast between its steps is what creates rhythm:

| Interval | Value | What it separates |
| --- | --- | --- |
| Page band | 32 px (`gap-8`) | The `PageHeader` from the body, and one band from the next |
| Panel | 24 px (`gap-6`) | Sibling cards, and the columns of a two-column page |
| Panel inset | 20 px | Owned by `SurfaceCard` — header, body, and footer all sit on it; pages do not restate it |
| Component content | 16 px (`gap-4`) | Fields, list rows, and value groups inside a panel |
| Section heading → content | 12 px (`gap-3`) | A bare `h2` and the thing it names |
| Control cluster | 8 px (`gap-2`) | A label and its input, a button pair |

A page grid that holds columns of unequal height needs `items-start` on the grid and `content-start` on each column. Grid's default `align-content: stretch` otherwise pours the taller column's surplus into the shorter one's rows, and every card in it grows a pocket of dead space at the bottom.

`HubLayout` owns application-page width and responsive gutters through its `standard`, `wide`, and `focused` variants; pages must not add a second outer `page-shell`. Sibling screens use the same variant — a list page that jumps from `standard` to `wide` on navigation reads as a different application. `wide` is for a genuinely twelve-column screen such as the dashboard. See [`application-shell.md`](application-shell.md) for the layout contract.

The workspace panel is flush: it runs to the top and right edges of the window with no margin, radius, or shadow of its own. The sidebar's right border is the only seam between navigation and content — a floating, rounded content card wastes edge space and reads as a demo rather than an application.

Forms should be one column by default. Data-heavy views can expand to a responsive grid, but related labels and values should stay visually grouped.

## Shape and elevation

- Base radius: 8 px (`--radius: 0.5rem`); cards sit one step above at 10 px (`--radius-card: 0.625rem`), controls one step below at 6 px (`rounded-md`), and chips and menu rows at 4 px (`rounded-sm`). Shape steps **down** as you nest — a control inside a panel is never rounder than the panel. `rounded-full` is reserved for things that are genuinely circular: avatars, status dots, count bubbles, and progress tracks.
- Borders establish structure and carry most of the elevation. `shadow-card` is a single 1px contact shadow that seats a panel on the page rather than floating it; only surfaces that genuinely cover the page (`shadow-popover`) get a real cast shadow. In dark mode a tinted shadow is invisible, so the tokens switch to black and separation comes from the surface step above the canvas plus the border.
- Ordinary cards carry `shadow-card`; interactive surfaces may lift one step (`shadow-card-hover`, `-translate-y-px`, 150 ms). Reserve heavier treatment for focused flows such as sign-in.

## Components and interaction

- **Buttons:** one primary action per region. The primary is the signature gold action — `brand-gold` with dark on-gold ink, 36 px tall and `rounded-md`, the same shape and height as the inputs it sits beside. Use `secondary` for a safe alternative, `outline` for lower-emphasis actions, `ghost` in navigation/toolbars, and `destructive` only for destructive work.
- **Forms:** labels remain visible above fields. Place validation messages directly below the field with `text-destructive`. Do not use placeholder text as a label.
- **Cards:** group one concept or task. Avoid nesting cards unless hierarchy would otherwise be ambiguous.
- **Badges:** use for short states or categories, not sentences. Pair semantic colors with explicit words such as “Approved” or “Overdue.” Every tone is a tinted surface behind a hairline of the same hue: the outline is what lets a chip read as a discrete object in a dense table row instead of a smudge of color behind the words. Surface, edge, and ink are **three declared tokens** (`--chip-<tone>`, `--chip-<tone>-edge`, and the tone's ink), never an alpha of the ink over the card. Alpha makes contrast context-dependent — the same `bg-x/10 text-x` pair that cleared AA on a white card fell below it on a dark one, because tinting a dark surface with the ink color drags the background *toward* the text. Every pair is verified at ≥4.5:1 against its own surface and against the card, in both themes; a new tone is not done until it is. `RoleBadge` colors itself from the **breadth of authority** a role carries, so a permission column separates by reach before it is read. Hue carries the category and lightness carries the ordering — broadest reads darkest — because lightness is the one channel every color-vision deficiency preserves, and the role name is always present as text so color is never the only code. `assigned_record` takes the neutral chip: it is the narrowest scope, and the gold it would otherwise claim belongs to actions — a gold badge beside a gold button splits the one color the page uses to say “press this”. The `--chart-*` ramp is for charts, not for ink: those values are mixed for large fills and several of them cannot reach 4.5:1 as 12 px text. The role name never truncates; only the scope that qualifies it gives way.
- **Tables:** right-align numbers, keep headers concise, and use a muted header surface. Cells carry vertical rules between columns — across a wide table the column edge is what keeps the eye on one record — and a column may declare an `icon` that names the *kind* of value it holds, so a reader finds the column they want before reading any header text. The icon is decorative; the header word remains the accessible name. Column headers render as 12 px micro-caps (`uppercase`, `tracking-[0.06em]`) so they read as labels rather than a first row of data. A table inside a card uses `frame="bleed"` — one frame, not two, with the row rules running to the card edges and the outer columns still aligned to the panel heading. Which columns survive a narrow panel is a **container** query, never a viewport breakpoint: a table in a 736 px column cannot see that the window is 1280 px wide. Columns declare `hideBelow` — the container width at which they stop fitting — and `DataTable` owns the class; a raw `hidden md:table-cell` in a column definition is a bug. Pick the step from the width the columns actually need, measured, not from a device. Below 576 px of table the rows become **cards**: a phone-width grid of eight columns is not a dense table but an unreadable one, and the card shows every column, including the ones the wide table drops. A table whose box still scrolls sideways exposes that box as a focusable, labelled region — columns past the edge are otherwise unreachable without a mouse (WCAG 2.1.1) — and only while it actually overflows, so a table that fits adds no tab stop. On narrow screens, prioritize or stack columns rather than shrinking text below 14 px.
- **Navigation:** keep the primary nav stable. The active item uses the sidebar accent surface, medium weight, a `text-primary` icon, and `aria-current="page"` — one treatment, not four. Hover takes the *same* surface at 55%: when hover and active shared a token, pointing at any row made it look like the page you were already on. Subsection headers are built to the nav row's own metrics so the rail reads as one column at three weights. Desktop and mobile render the same filtered `HUB_NAV_REGISTRY`; the uppercase group label is the only top-level separation. Permission requirements use the effective permission union, never role labels. Explicitly registered disabled modules remain visible to authorized users, gathered into one collapsed **Coming soon** disclosure at the foot of the rail rather than scattered through the live groups — each keeps its link, its quiet “Soon” marker, and its spoken description, so nothing is taken away from a reader who goes looking, but every group heading now names work that exists. A group whose every item is pending disappears.  missing feature keys, unknown permissions, and office-scoped items without office context fail closed. Administrative subsections are keyboard-operable collapsibles drawn as a branch of the rail — a trunk and one tick per destination, both folded away on the icon rail; the active subsection remains exposed, and icon-only mode supplies a tooltip for every authorized destination. See [`navigation.md`](navigation.md) for the contributor contract.
- **Sidebar footer:** the signed-in identity sits in one account card — avatar, name, email, and sign out. The name block links to the profile rather than opening a second menu, and the card collapses to the avatar alone on the icon rail.
- **Text over imagery:** copy laid directly on a photograph uses `.on-media-ink` — a fixed light ink (`--on-media`, the same in both themes, because a photograph is not a themed surface) with a shadow on the glyphs rather than a scrim, gradient, or panel behind them. The image is then shown exactly as uploaded. This is a weaker contrast guarantee than a scrim, so it is reserved for **decorative** artwork whose words also exist as ordinary text elsewhere on the page; never put the only copy of something over an image.
- **Icon tiles:** one tile vocabulary via `IconWell`. `tone="brand"` (gold) marks a small, countable set of brand moments — the quick-access launchers, the empty-state mark. `tone="muted"` is available for a one-off neutral tile. Panel headings carry **no** tile: the heading identifies the panel, and a tile repeated beside every title on a page competes with the data underneath it.
- **Create drawers:** making one new thing from a list page uses `CreateSheet` — the standard right-hand slide-over, opened in place rather than navigated to, so the queue the author was reading stays visible behind it. It posts as a **native form**, not through the Inertia router: multipart uploads need no second code path, and nothing typed sits in client state that a failed save could lose. The whole server contract is one hidden field — `context=sheet` tells the create view to answer 422 with the *list* page, drawer reopened and draft echoed back, instead of the standalone form page it renders for a direct visit. Ask only for what the record needs in order to exist and be aimed at somebody, then redirect to its own page on success; previews, lifecycle actions, and anything wanting full width or a persistent side panel belong there, not in a narrower column. `FormSheet` / `FormSheetBody` remain available for slide-overs that are not a create.
- **Native selects:** a form that posts to Django (see `CreateSheet`) uses `NativeSelect`, not a bare `<select>` and not a private `SELECT_CLASS` constant. It is a real `<select>` wearing the `Input` recipe — same 36 px height, `rounded-md`, `px-3`, focus ring, disabled state — with the OS chevron replaced by the Lucide one, so a select and the input beside it in the same row are visibly the same control. Reach for the Radix `Select` only when the value is client state and the options need styling.
- **Standing notes:** one sentence of context about a page or a section — what a reader may do here, what an edit will change, why a control is unavailable — renders through `Callout`, in the same tinted-surface-behind-a-hairline vocabulary as a status chip, one size up. `neutral` is the default because most notes are orientation, not alarm; a colored tone means something to do or decide, and at most one control sits on the trailing edge. A field's validation message belongs under the field, not in a banner. Never hand-roll a note out of `SurfaceCard` plus a literal `bg-warning/8`.
- **Empty states:** every way a surface can end with nothing on it — a genuine zero, a module that is not connected, a provider that failed, a panel the reader's access does not cover — renders through `EmptyState`, so a dashboard of half-connected modules reads as one deliberate page rather than five different apologies. It draws its mark through `IconWell`, so it has the same six tones as every other tile in the system: `tone="brand"` (gold well) invites the reader to put the first thing there, `tone="muted"` is for an absence they cannot act on, and the semantic tones classify *why* the surface is empty when that is worth saying.
- **Metric bands:** stat cards auto-fit between a floor and a ceiling rather than a fixed four-up. The count varies per reader because figures are permission- and source-filtered: the floor keeps four across a wide band, and the ceiling stops a lone figure from stretching into a billboard whose label and mark sit a screen apart. A band's scope and freshness are one footnote line under it, never a stack of stranded captions.
- **Filters:** `FilterControls` is the one filter surface on a list page: the search field, a toggle carrying the count of what is narrowing the list, the fields themselves, and a reset that exists only while there is something to reset. A page has one filter surface, never a visible row plus a second disclosure below it.
  - The panel starts **closed**. Filtering is the exception on most visits, and an untouched list should open as a search box and a button, not as a wall of empty dropdowns.
  - It starts **open when something is already filtering** (`activeCount > 0`), which is what keeps a reader from blaming the data for a constraint they cannot see. After that the state is theirs — applying a filter from inside the panel never slams it shut, and clearing the last one never hides the fields still in use.
  - Search rides the toggle's row through the `leading` prop. Searching and filtering are the same job; stacking them cost a row of every list page to say so twice.
  - Each field's control names its own dimension in its resting state ("Any office"), so `FilterField` takes `hideLabel` and the printed label goes to screen readers only. A date or free-text field keeps its label — nothing inside it says what it is.
  - Pass `collapsible={false}` where the fields are the page's primary control, as on a report.
- **Pagination:** the pager lists page numbers with the first, the last, and a window around the current one, eliding the rest. A control that only says “next” hides where the reader is; one that lists ninety pages is a wall.
- **Page headers:** `PageHeader` renders the title, an optional description, breadcrumbs, static `meta`, and `actions`. There is deliberately **no eyebrow/kicker slot**: a label stacked above the heading either repeats the shell's own title and breadcrumb or says less than the heading it interrupts. Give the heading the words it needs instead.
- **Icon tiles:** one tile vocabulary via `IconWell`, in six tones. `brand` (gold) marks a small, countable set of brand moments; `muted` is the neutral tile. The five semantic tones — `info`, `success`, `warning`, `destructive`, `neutral` — are the *same* verified surface/ink pairs the status chips use, so a tile that classifies something carries colour meaning exactly what the chip beside it means and clears 4.5:1 in both themes for free. A tone is not decoration: if the colour is not encoding something a reader could act on, it is `muted`.
- **Tinted surfaces:** never an alpha of the ink that sits on them. `bg-destructive/10 text-destructive` reads fine on a white card and fails on a dark one, because tinting a dark surface with the ink colour drags the background toward the text. Use the declared `--chip-<tone>` / `--chip-<tone>-edge` / ink triple — that is what they exist for, and every pair is verified against its own surface and the card in both themes.
- **Metric rows:** a row of figures is one `MetricStrip`, not a grid of bordered `MetricCard`s. The strip is a single surface divided by hairlines — the rules that run between table columns, turned on a row of numbers — so the figures share a baseline and the page carries one object instead of four. Cells auto-fit, so the same strip is four across on a monitor and one across on a phone with no breakpoint. `MetricCard` defaults to `frame="cell"` for exactly this; `frame="card"` re-adds a border for the rare figure that genuinely stands alone. The strip clips its corners, so a drill-through cell takes a negatively-offset **outline** for focus, never a ring — a box-shadow would be clipped away on the outermost cells.
- **Page mastheads:** `PageHeader` takes `rule` to close the block with a hairline. Earned when the page below is a continuous ruled workspace; a page of detached cards does not need it. Controls belong in the header's own `actions` slot, not in a sibling flex beside it, or the rule spans half the page.
- **Panel headers:** use `PanelHeader` — heading, optional description, and at most one right-hand slot: `meta` for a static fact or `action` for a real control. Static facts render through `SurfaceCardMeta` as plain muted type, never a pill or a chevron, so they cannot pose as a dropdown.
- **Badges:** `warning` uses `text-warning-ink` over the tint, never `--warning-foreground` — that token is the ink for a *solid* warning surface and disappears on a dark card.
- **Timelines:** the default marker is a toned dot; `current` widens its ring. Pass `icon` only where the mark means something — a check on a step that is genuinely complete. A check on every entry claims progress the data does not support.
- **Interactive cards and rows:** one response, and it happens in place — the border firms to `border-strong`, a faint accent wash comes up, the trailing icon goes to full ink, 150 ms. A panel that lifts a pixel and grows a shadow is the floating-card gesture this system spends its shape and depth budget avoiding; a row in a dense list should not take off under the pointer.
- **Arrival motion:** deferred content uses the `.arrive` utility (240 ms rise + fade). Use an animation, never a transition from a hidden default, so content stays visible if it never runs.
- **Route progress:** `HubLayout` shows a 2px gold sweep on the header's bottom border while an Inertia visit is in flight. It is the only sighted signal that a request is out — a visit swaps the page without a browser navigation, so no chrome moves on its own — and it pairs with the polite `aria-busy`/status already on the content region. Indeterminate, never filling: the client does not know how far along the request is.

All interactive controls need a visible focus ring, a minimum practical target of 36 px (44 px on touch-heavy screens), a disabled state, and clear hover/pressed feedback. Animations should generally stay between 120–200 ms. `app.css` carries the global `prefers-reduced-motion` path so individual components do not repeat it, and that path **reduces rather than disables**: transitions keep easing but only over colour, border, opacity, and shadow, so hover, focus, and press still read as feedback while transforms land instantly. The three indeterminate indicators — spinner, pulse, and the route bar — are exempt and keep looping more slowly: a stopped progress indicator does not read as reduced motion, it reads as hung. A loop that seeks attention rather than reporting progress (`animate-ping`) stops.

## Browser surfaces

The parts of the page nobody draws still carry the design, and left at their defaults they are the only pixels on screen that came from somewhere else. `app.css` themes them once, globally; a component never restates them:

| Surface | Treatment |
| --- | --- |
| Scrollbar | 10px, `--border-strong` thumb inset on a transparent track, `--muted-foreground` on hover. Firefox's `scrollbar-color` and the WebKit pseudo-elements are both stated |
| Selection | 35% gold wash, `color` stated outright because the ink differs between themes |
| Caret | `--primary` |
| `accent-color` | Brand gold, so a native date picker or browser-owned control agrees with the app |
| Autofill | Chrome's wash overridden with a 1000px inset shadow in `--card` plus the 10000s transition that holds it |
| `::marker`, `::placeholder` | `--muted-foreground` |
| Widows | `text-wrap: pretty` on `p`/`li`, `text-balance` on headings |
| Scroll | Smooth, with `scroll-margin-block: 5rem` so a focused or `:target` element clears the sticky header |

**Print.** The rail and the top bar carry `print:hidden`; `@media print` drops fills and shadows, forces black on white, repeats `thead` per page, and holds rows, images, and quotes off break boundaries. A brokerage prints contracts, reports, and rosters, and none of them need navigation on paper.

**Forced colors.** Windows High Contrast drops background colours, which would take with it every border defined as one. Cards, table containers, inputs, select triggers, and badges restate their border in `CanvasText`, and `:focus-visible` takes a `Highlight` outline.

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
