---
name: oNEST HUB
description: Warm, dense operational interface for a real-estate brokerage intranet.
colors:
  brand-gold: "#ddb52a"
  brand-gold-deep: "#c39a15"
  brand-gold-soft: "#fbf5df"
  brand-on-gold: "#231a00"
  brand-ink: "#0d0d0d"
  background: "oklch(0.985 0.006 80)"
  foreground: "oklch(0.22 0.018 72)"
  card: "oklch(1 0 0)"
  card-foreground: "oklch(0.22 0.018 72)"
  popover: "oklch(1 0 0)"
  muted: "oklch(0.96 0.008 78)"
  muted-foreground: "oklch(0.49 0.018 72)"
  secondary: "oklch(0.95 0.019 78)"
  secondary-foreground: "oklch(0.31 0.045 72)"
  accent: "oklch(0.92 0.04 78)"
  accent-foreground: "oklch(0.31 0.055 72)"
  primary: "oklch(0.5 0.115 74)"
  primary-foreground: "oklch(0.99 0.004 80)"
  success: "oklch(0.49 0.12 150)"
  warning: "oklch(0.68 0.14 70)"
  warning-ink: "oklch(0.45 0.115 68)"
  info: "oklch(0.52 0.13 245)"
  destructive: "oklch(0.56 0.2 27)"
  border: "oklch(0.89 0.014 78)"
  border-strong: "oklch(0.78 0.02 76)"
  input: "oklch(0.86 0.018 78)"
  ring: "oklch(0.61 0.12 76)"
  sidebar: "oklch(0.975 0.01 78)"
  sidebar-accent: "oklch(0.92 0.04 78)"
  chip-neutral: "oklch(0.96 0.008 78)"
  chip-neutral-edge: "oklch(0.89 0.014 78)"
  chip-primary: "oklch(0.965 0.027 74)"
  chip-primary-edge: "oklch(0.88 0.043 74)"
  chip-success: "oklch(0.965 0.027 150)"
  chip-success-edge: "oklch(0.88 0.043 150)"
  chip-info: "oklch(0.965 0.017 245)"
  chip-info-edge: "oklch(0.88 0.043 245)"
  chip-warning: "oklch(0.965 0.023 68)"
  chip-warning-edge: "oklch(0.88 0.043 68)"
  chip-destructive: "oklch(0.965 0.017 27)"
  chip-destructive-edge: "oklch(0.88 0.043 27)"
  chip-role-company: "oklch(0.965 0.017 244)"
  role-company-ink: "oklch(0.44 0.111 244)"
  chip-role-region: "oklch(0.965 0.017 42)"
  role-region-ink: "oklch(0.48 0.139 42)"
  chip-role-office: "oklch(0.965 0.027 153)"
  role-office-ink: "oklch(0.5 0.129 153)"
  chip-role-protected: "oklch(0.965 0.021 310)"
  role-protected-ink: "oklch(0.46 0.139 310)"
typography:
  display:
    fontFamily: "Plus Jakarta Sans Variable, Plus Jakarta Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "2.5rem"
    fontWeight: 700
    lineHeight: "3rem"
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Plus Jakarta Sans Variable, Plus Jakarta Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(1.625rem, 2.6vw, 2rem)"
    fontWeight: 700
    letterSpacing: "-0.03em"
  title:
    fontFamily: "Plus Jakarta Sans Variable, Plus Jakarta Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 700
    lineHeight: "1.75rem"
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Plus Jakarta Sans Variable, Plus Jakarta Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: "1.25rem"
  label:
    fontFamily: "Plus Jakarta Sans Variable, Plus Jakarta Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: "1rem"
    letterSpacing: "0.02em"
  micro:
    fontFamily: "Plus Jakarta Sans Variable, Plus Jakarta Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 600
    lineHeight: "1rem"
    letterSpacing: "0.02em"
  metric:
    fontFamily: "Plus Jakarta Sans Variable, Plus Jakarta Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 700
    lineHeight: "2.25rem"
    letterSpacing: "-0.02em"
rounded:
  sm: "0.625rem"
  md: "0.75rem"
  lg: "0.875rem"
  xl: "1.125rem"
  2xl: "1.375rem"
  card: "1.25rem"
  full: "9999px"
spacing:
  base: "4px"
  control: "8px"
  section: "12px"
  component: "16px"
  panel: "24px"
  band: "40px"
components:
  button-primary:
    backgroundColor: "{colors.brand-gold}"
    textColor: "{colors.brand-on-gold}"
    rounded: "{rounded.full}"
    padding: "0.5rem 1.25rem"
    height: "2.5rem"
  button-primary-hover:
    backgroundColor: "{colors.brand-gold-deep}"
    textColor: "{colors.brand-on-gold}"
  button-outline:
    backgroundColor: "{colors.card}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.full}"
    padding: "0.5rem 1.25rem"
    height: "2.5rem"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.foreground}"
    rounded: "{rounded.full}"
    height: "2.5rem"
  input:
    backgroundColor: "transparent"
    textColor: "{colors.foreground}"
    rounded: "{rounded.lg}"
    padding: "0.5rem 0.875rem"
    height: "2.5rem"
  card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.card-foreground}"
    rounded: "{rounded.card}"
    padding: "1.5rem"
  chip-status:
    backgroundColor: "{colors.chip-success}"
    textColor: "{colors.success}"
    typography: "{typography.label}"
    rounded: "{rounded.full}"
    padding: "0.25rem 0.625rem"
  chip-role:
    backgroundColor: "{colors.chip-role-office}"
    textColor: "{colors.role-office-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.full}"
    padding: "0.25rem 0.625rem"
  table-head:
    backgroundColor: "{colors.muted}"
    textColor: "{colors.muted-foreground}"
    typography: "{typography.label}"
    height: "2.75rem"
    padding: "0 1rem"
---

# Design System: oNEST HUB

> **Scope.** This file is the **token and visual-world source of truth**: what the
> colors, type, shape, and depth values *are*, and the character they add up to.
> The **component contract** — per-component APIs, states, accessibility
> expectations, and change policy — lives in
> [`docs/design-system.md`](docs/design-system.md), which `CLAUDE.md` points
> contributors to. When the two disagree about a value, this file wins; when
> they disagree about a component's behavior, that file wins. Neither may
> silently contradict the implementation in `frontend/css/app.css`.

## Overview

**Creative North Star: "The Daylit Ledger"**

This is a record that people keep all day, in a warm room. The surface is ivory
rather than white, the rules between columns are hairlines rather than borders,
and the one saturated color in the building — oNEST gold — is spent on actions
and brand moments, never on decoration. A brokerage runs on tables: who is in
which office, which contract is unsigned, which license expires this month. The
system's whole job is to make that legible for eight hours without going cold.

Density is deliberate and so is the warmth that offsets it. Every neutral is
tilted toward hue 72–80, so a screen full of gray type still reads as paper and
not as a spreadsheet. Depth comes from tonal layering and very diffuse ambient
shadow, never from hard offsets: surfaces rest on the background rather than
float above it. Structure comes from borders, and borders are 1px.

Restraint is the mechanism, not the goal. Because almost nothing is colored,
a single gold pill or a tinted status chip carries real information the moment
it appears.

**Key Characteristics:**

- Warm ivory canvas (`#fbf9f3`-family) with pure white raised surfaces
- oNEST gold as a rare signal — actions and brand, not state
- Hairline structure; two-layer, low-opacity ambient shadow for elevation
- Fully-rounded controls against 20px cards — the pill is the control shape
- A single 4px spacing ladder whose *contrast between steps* creates rhythm
- Status and category encoded as tinted surface + matching hairline + ink

## Colors

A warm, low-chroma neutral field with one saturated brand hue and a tightly
governed set of semantic tints.

### Primary

- **oNEST Gold** (`#DDB52A`): the signature. The logo, the primary call to
  action, the active navigation rail, and the `brand-well` behind an icon mark.
  It is a *brand* color, not a state color — a gold chip beside a gold button
  splits the one color the page uses to say "press this."
- **Primary** (`oklch(0.5 0.115 74)`): the readable, contrast-adjusted step of
  the same hue, used for links, active navigation type, and any gold that has to
  survive as text. Gold at its brand lightness cannot.

### Neutral

- **Warm Ivory** (`oklch(0.985 0.006 80)`): the application canvas. Never white.
- **Card** (`#FFFFFF`): raised content surfaces, and the only pure white here.
- **Deep Charcoal** (`oklch(0.22 0.018 72)`): body and heading ink.
- **Muted Text** (`oklch(0.49 0.018 72)`): descriptions, metadata, table
  headers, and inactive icons.
- **Border** (`oklch(0.89 0.014 78)`): the hairline that carries all structure.
  **Border Strong** (`oklch(0.78 0.02 76)`) is available where a rule must
  separate two dense regions rather than merely group them.

### Semantic

- **Success** (`oklch(0.49 0.12 150)`), **Info** (`oklch(0.52 0.13 245)`),
  **Destructive** (`oklch(0.56 0.2 27)`): completion, neutral notice, and error.
- **Warning** (`oklch(0.68 0.14 70)`) is a **surface** tint; **Warning Ink**
  (`oklch(0.45 0.115 68)`) is the text step. As type on a card the surface value
  reaches only about 2.4:1, which is why the pair exists.

### Category

Role chips are colored by breadth of authority: company, region, office, and a
reserved tone for protected roles, each with its own ink token. The narrowest
scope takes the neutral chip. The `--chart-*` ramp is for charts only — those
values are mixed for large fills and several cannot reach 4.5:1 as 12px text.

### Named Rules

**The Spent Gold Rule.** Gold marks brand and action. The moment it also marks
state, it stops meaning "press this" and the page loses its one loud signal.

**The Two-Token Rule.** Every tinted surface declares its ink separately.
Nothing derives a chip background from an alpha of its own text color — alpha
makes contrast context-dependent, and the pair that clears AA on a white card
fails it on a dark one.

**The Verified Pair Rule.** A new tone is not finished until its ink clears
4.5:1 against its own surface *and* against the card, in both themes.

## Typography

**Display / Body / Label Font:** Plus Jakarta Sans (self-hosted variable cut),
falling back to the platform sans-serif.
**Mono:** SF Mono / Consolas, for code and measurement only.

**Character:** One family doing all the work, separated by weight and tracking
rather than by contrast of form. Headings run 600–700 with tight negative
tracking; labels run 600 with slightly open tracking. The result is a voice that
reads as engineered rather than composed — appropriate for a page that is mostly
data.

### Hierarchy

- **Display** (700, 40px/48px, -0.02em): rare hero copy.
- **Headline** (700, clamp 26–32px, -0.03em): the one page title, via `PageHeader`.
- **Title** (700, 18px/28px, -0.02em): page sections and panel headings.
- **Body** (400, 14px/20px; 16px/24px for long-form): interface and prose.
- **Label** (600, 12px, 0.02em): form and data labels; table column headers add
  uppercase and 0.06em.
- **Micro** (600, 11px, 0.02em): chrome only — sidebar group labels,
  breadcrumbs, keycaps, counters.
- **Metric** (700, 28px/36px, -0.02em, tabular): stat figures.

### Named Rules

**The Measure Rule.** Prose caps at `max-w-measure` (34rem ≈ 70 characters at
the 14px body step). The cap belongs on the paragraph, not on the column holding
it — a description should stop before its container does.

**The Floor Rule.** `micro` (11px) is the smallest step and it is *chrome*:
labels that name a region, never content a reader must read. A literal
`text-[10px]` is a bug.

## Layout

A single 4px scale, where the **contrast between steps** is what creates rhythm:
control cluster 8px, heading-to-content 12px, component content 16px, sibling
panels 24px, page band 40px. Panels own their header-to-body inset (20px);
pages do not restate it.

`HubLayout` owns page width and responsive gutters through `standard`, `wide`,
and `focused` variants — pages never add a second outer shell, and sibling
screens use the same variant so navigation does not feel like a different
application. The workspace panel is flush to the top and right edges of the
window; the sidebar's right border is the only seam.

Responsive behavior is **container-driven, not viewport-driven**. A table in a
736px panel cannot see that the window is 1280px wide, so columns declare the
container width below which they stop fitting, and below 576px of table the rows
become cards that show every column. Forms are one column by default.

### Named Rules

**The Container Rule.** Anything whose fit depends on the space it actually
occupies asks a container query. A viewport breakpoint in a panel is a bug.

## Elevation & Depth

Tonal layering first, shadow second. The canvas is warm ivory, raised surfaces
are white, and the step between them plus a 1px border does most of the work.
Shadows are soft, layered, ambient light — two low-opacity layers with a large
blur and almost no offset — so a card appears to *rest* on the background rather
than float above it. There are no hard offsets and no dark halos anywhere.

### Shadow Vocabulary

- **Card** (`0 1px 2px oklch(0.2 0.01 72 / 4%), 0 8px 24px oklch(0.2 0.01 72 / 5%)`):
  every ordinary raised surface.
- **Card hover** (`0 2px 6px … / 4%, 0 16px 40px … / 9%`): one step up, paired
  with a 1px lift over 150ms, for genuinely interactive surfaces only.
- **Popover** (`0 18px 48px oklch(0.16 0.01 72 / 14%)`): menus, dialogs, and
  anything that must read as detached from the page.

### Named Rules

**The Resting Rule.** Elevation answers a state change — hover, focus, detach.
A surface that never responds gets `shadow-card` and nothing more.

## Shapes

Fully-rounded controls against generously-rounded containers. Base radius is
14px (`--radius`); cards step up to 20px (`--radius-card`); buttons, badges, and
pills are fully rounded, because **the pill is the control shape** and it is what
separates something pressable from something readable at a glance. Inputs and
selects take the 14px base so a field and the button beside it are visibly the
same family without pretending to be the same control.

Borders establish structure everywhere: 1px, `--border`, and enough of them that
removing shadow entirely would leave the layout intact.

### Named Rules

**The Pill Rule.** If it can be pressed, it is fully rounded. If it holds
content, it has a radius. Nothing in this system has square corners.

## Components

**Character: warm precision.** Exact spacing and hairline structure, softened by
warm neutrals and fully-rounded controls. Nothing is ornamental; the warmth comes
from the palette and the radius, not from decoration.

### Buttons

- **Shape:** fully rounded (`9999px`), 40px tall (36px `sm`, 44px `lg`).
- **Primary:** oNEST gold with near-black on-gold ink (`#231a00`), no border.
  One per region. Hover deepens to `#c39a15`; press scales to 0.98.
- **Secondary / Outline / Ghost:** warm neutral fill, 1px border on card, and
  bare respectively — in descending emphasis. Ghost is the toolbar and
  navigation default.
- **Destructive:** solid, reserved for irreversible work.
- **Focus:** 3px `--ring` halo plus a border shift; never removed.

### Chips & Badges

- **Style:** a tinted surface behind a hairline of the same hue, fully rounded,
  12px semibold label, 4px/10px padding.
- **Status:** semantic tone plus an explicit word and, where available, an icon —
  never color alone.
- **Role:** colored by breadth of authority; hue carries the category and
  lightness carries the ordering, since lightness is the one channel every
  color-vision deficiency preserves.

### Cards / Containers

- **Corner:** 20px (`--radius-card`). **Background:** white on ivory.
- **Border:** 1px `--border`. **Shadow:** `shadow-card` (see Elevation).
- **Padding:** 24px. Group one concept; never nest cards.

### Inputs / Fields

- **Style:** transparent fill, 1px `--input` border, 14px radius, 40px tall.
- **Focus:** border shifts to `--ring` with a 3px halo.
- **Labels** stay visible above the field; validation sits directly below it in
  `--destructive`. Placeholder text is never a label.

### Tables

- Muted header surface, 12px uppercase micro-caps column labels at 0.06em, 44px
  header row, 1px horizontal rules, and vertical rules between cells so a wide
  row stays readable across the screen. Numbers right-align and run tabular.
  Row hover is a muted wash (`--muted` at 40%).

### Navigation

- Vertical sidebar on a slightly tinted surface with a hairline right border.
  The active item takes the sidebar accent surface, semibold type, a
  `--primary` icon, and a 4px gold rail on its leading edge. Subsections draw a
  connector trunk with a tick per destination, both folded away on the icon rail.

## Do's and Don'ts

### Do:

- **Do** spend gold on actions and brand moments only — the primary button, the
  active nav rail, the `brand-well` icon tile, the sign-in call to action.
- **Do** declare a tinted surface and its ink as separate tokens, and verify the
  pair at 4.5:1 against its own surface and the card, in both themes.
- **Do** pair every status color with an explicit word, and an icon where one
  exists.
- **Do** let borders carry structure and keep shadows ambient — two layers, low
  opacity, large blur, almost no offset.
- **Do** ask a container query for anything whose fit depends on the space it
  actually occupies.
- **Do** use the semantic tokens in `frontend/css/app.css`; both themes switch
  together through them.

### Don't:

- **Don't** put a literal hex in a component. A raw color outside `app.css` is a
  bug.
- **Don't** build a chip surface from an alpha of its own ink — contrast then
  depends on whatever sits behind it.
- **Don't** use the `--chart-*` ramp as text. Those values are mixed for large
  fills and several cannot reach 4.5:1 at 12px.
- **Don't** use `--warning` as type, or `--warning-foreground` anywhere but on a
  solid warning surface.
- **Don't** reach for a viewport breakpoint to decide what fits inside a panel.
- **Don't** give a card a hard offset shadow, a colored left border above 1px, or
  a second nested card.
- **Don't** go below the 11px `micro` step, and don't use it for content.
