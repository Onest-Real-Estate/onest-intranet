---
name: oNEST HUB
description: Clean, dense operational interface for a real-estate brokerage intranet.
colors:
  brand-gold: "#ddb52a"
  brand-gold-deep: "#c39a15"
  brand-gold-soft: "#fbf5df"
  brand-on-gold: "#231a00"
  brand-ink: "#0d0d0d"
  background: "oklch(1 0 0)"
  foreground: "oklch(0.21 0.003 286)"
  card: "oklch(1 0 0)"
  card-foreground: "oklch(0.21 0.003 286)"
  popover: "oklch(1 0 0)"
  muted: "oklch(0.968 0.002 286)"
  muted-foreground: "oklch(0.51 0.005 286)"
  secondary: "oklch(0.968 0.002 286)"
  secondary-foreground: "oklch(0.3 0.004 286)"
  accent: "oklch(0.955 0.003 286)"
  accent-foreground: "oklch(0.28 0.004 286)"
  primary: "oklch(0.5 0.115 74)"
  primary-foreground: "oklch(0.99 0.004 80)"
  success: "oklch(0.49 0.12 150)"
  warning: "oklch(0.68 0.14 70)"
  warning-ink: "oklch(0.45 0.115 68)"
  info: "oklch(0.52 0.13 245)"
  destructive: "oklch(0.56 0.2 27)"
  border: "oklch(0.917 0.003 286)"
  border-strong: "oklch(0.8 0.004 286)"
  input: "oklch(0.885 0.004 286)"
  ring: "oklch(0.61 0.12 76)"
  sidebar: "oklch(0.982 0.002 286)"
  sidebar-accent: "oklch(0.945 0.003 286)"
  chip-neutral: "oklch(0.968 0.002 286)"
  chip-neutral-edge: "oklch(0.9 0.003 286)"
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
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: "2rem"
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Plus Jakarta Sans Variable, Plus Jakarta Sans, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: "1.5rem"
    letterSpacing: "-0.01em"
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
  sm: "0.25rem"
  md: "0.375rem"
  lg: "0.5rem"
  xl: "0.75rem"
  2xl: "1rem"
  card: "0.625rem"
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
    rounded: "{rounded.md}"
    padding: "0.5rem 1rem"
    height: "2.25rem"
  button-primary-hover:
    backgroundColor: "{colors.brand-gold-deep}"
    textColor: "{colors.brand-on-gold}"
  button-outline:
    backgroundColor: "{colors.card}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    padding: "0.5rem 1rem"
    height: "2.25rem"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    height: "2.25rem"
  input:
    backgroundColor: "transparent"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    padding: "0.25rem 0.75rem"
    height: "2.25rem"
  card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.card-foreground}"
    rounded: "{rounded.card}"
    padding: "1.25rem"
  chip-status:
    backgroundColor: "{colors.chip-success}"
    textColor: "{colors.success}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: "0.125rem 0.5rem"
  chip-role:
    backgroundColor: "{colors.chip-role-office}"
    textColor: "{colors.role-office-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: "0.125rem 0.5rem"
  metric-strip:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.card}"
    divider: "1px solid {colors.border}"
    cellPadding: "1rem 1.25rem"
  table-head:
    backgroundColor: "{colors.muted}"
    textColor: "{colors.muted-foreground}"
    typography: "{typography.micro}"
    height: "2.5rem"
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

**Creative North Star: "The Clean Ledger"**

This is a record people keep all day, and the paper is white. The canvas is
white, the panels on it are white, and what separates them is a 1px rule — the
same rule that runs between the columns of a table. A brokerage runs on tables:
who is in which office, which contract is unsigned, which license expires this
month. The system's whole job is to make that legible for eight hours.

The neutrals are genuinely neutral. An earlier version tilted every grey toward
hue 72–80 to keep the screen warm; at one panel that reads as warmth, but across
a full page of them it reads as a yellow cast on white paper. The greys now
carry 0.002–0.005 chroma — enough that a panel beside the brand gold does not
turn faintly blue by contrast, not enough to be a colour.

That leaves gold with a job. It is the fill on the **one primary action per
region**, the mark in the logo, the icon beside the active navigation item, the
focus ring, and the caret. Nowhere else. On a page where every other surface is
white or grey, that is the loudest possible signal — and it costs one colour.

**Key Characteristics:**

- White canvas, white panels, 1px rules doing the separating
- Neutral greys — no hue cast across the field
- oNEST gold spent on one thing per screen: the action worth pressing
- Hairline structure; the 1px border carries elevation and a single 1px contact
  shadow finishes it. Dark mode drops the tint and separates on surface step
- 6px controls inside 10px panels — shape steps down as you nest, never up
- A single 4px spacing ladder whose *contrast between steps* creates rhythm
- Status and category encoded as tinted surface + matching hairline + ink

## Colors

A neutral field with one saturated brand hue and a tightly governed set of
semantic tints.

### Primary

- **oNEST Gold** (`#DDB52A`): the signature. The logo, the primary call to
  action, the active navigation icon, the focus ring, and the `brand-well`
  behind an icon mark. It is a *brand* color, not a state color — a gold chip
  beside a gold button splits the one color the page uses to say "press this."
  It is also **secondary in area**: on a finished screen gold should occupy one
  button and a 3px rail, and nothing else.
- **Primary** (`oklch(0.5 0.115 74)`): the readable, contrast-adjusted step of
  the same hue, used for links, active navigation type, and any gold that has to
  survive as text. Gold at its brand lightness cannot.

### Neutral

- **White** (`oklch(1 0 0)`): both the application canvas and the panels on it.
  They are the same value on purpose — the border is what separates them, and a
  panel that also needed a tonal step would be a panel the border was failing.
- **Ink** (`oklch(0.21 0.003 286)`): body and heading type.
- **Muted Text** (`oklch(0.51 0.005 286)`): descriptions, metadata, table
  headers, and inactive icons. 5.75:1 on white.
- **Border** (`oklch(0.917 0.003 286)`): the hairline that carries all
  structure. **Border Strong** (`oklch(0.8 0.004 286)`) is available where a
  rule must separate two dense regions rather than merely group them.
- **Muted surface** (`oklch(0.968 0.002 286)`): table header bands, recessed
  wells, read-only panels — the one tonal step, used where a region has to
  recede rather than be enclosed.
- **Sidebar** (`oklch(0.982 0.002 286)`): one step off white, so the rail reads
  as chrome beside the workspace without becoming a second colour.

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

**The Neutral Field Rule.** Greys stay under 0.006 chroma. A hue tilt that
flatters one card becomes a cast across a page of them, and the cast competes
with the only colour that is supposed to be saying anything.

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
- **Headline** (700, 24px/32px, -0.02em): the one page title, via `PageHeader`.
  **Fixed, not fluid.** A viewport-scaled title is a landing-page device: it
  assumes the page is the thing being looked at. An operational screen is
  looked *through*, and a heading that grows with the window only pushes the
  data further down a wide monitor where there was already room.
- **Title** (600, 16px/24px, -0.01em): page sections and panel headings. A clear
  step under the page title — twenty panel headings at the headline's weight
  make a page of competing mastheads with no page title left.
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

Tonal layering and the 1px border do nearly all of the work. The canvas is warm
ivory, raised surfaces are white, and the step between them plus a hairline is
what separates a panel from the page. Shadow is the finish, not the mechanism:
one tight contact shadow seats a surface, and only something that genuinely
*covers* the page casts a real one.

The previous system spent a 24px blur under every card. At twenty panels that
stops reading as depth and starts reading as haze — every surface equally soft,
so nothing is actually raised relative to anything else. A crisp edge is more
convincingly a plane than a large diffuse one.

### Shadow Vocabulary

- **Card** (`0 1px 2px oklch(0.2 0.01 72 / 5%)`): every ordinary raised surface.
  One layer, one pixel of offset, no bloom.
- **Card hover** (`0 1px 2px … / 6%, 0 4px 12px … / 7%`): one step up, paired
  with a 1px lift over 150ms, for genuinely interactive surfaces only.
- **Popover** (`0 2px 4px … / 6%, 0 12px 32px … / 12%`): menus, dialogs, and
  anything that must read as detached from the page.

**Dark mode inverts the mechanism.** A warm-tinted shadow is invisible against a
dark canvas, so the dark tokens switch to black and separation comes from the
surface step above the canvas plus the border. The tokens carry this; no
component special-cases it.

### Named Rules

**The Resting Rule.** Elevation answers a state change — hover, focus, detach.
A surface that never responds gets `shadow-card` and nothing more.

**The Rule Before The Box Rule.** Reach for a hairline before a container. Four
bordered cards in a row float four ways and invite the eye to compare their
*edges*; one ruled strip puts the figures on a common baseline and is one object
on the page instead of four. `MetricStrip` is the built form of this.

## Shapes

Shape steps **down** as you nest. Panels are 10px (`--radius-card`), the base
radius is 8px (`--radius`), controls sit at 6px (`rounded-md`), and chips and
menu rows at 4px (`rounded-sm`). A control is never rounder than the panel
holding it — concentric radii that grow inward are the single clearest tell of
an interface assembled rather than drawn.

`rounded-full` is reserved for things that are genuinely circular: avatars,
status dots, count bubbles, progress tracks. A pill-shaped
button is a consumer-app gesture; at the density this product runs, it costs
horizontal room on every toolbar and makes a row of controls read as a row of
tags.

Borders establish structure everywhere: 1px, `--border`, and enough of them that
removing shadow entirely would leave the layout intact.

### Named Rules

**The Nesting Rule.** Radius decreases inward, never increases. If a container
and its contents share a radius, one of them is wrong.

**The Circle Rule.** `rounded-full` means the thing *is* a circle. Anything with
two different dimensions takes a step from the ladder.

## Components

**Character: warm precision.** Exact spacing and hairline structure, softened by
warm neutrals and fully-rounded controls. Nothing is ornamental; the warmth comes
from the palette and the radius, not from decoration.

### Buttons

- **Shape:** `rounded-md` (6px), 36px tall (32px `sm`, 40px `lg`) — the same
  height and radius as the input beside it, so a control row reads as one row.
- **Primary:** oNEST gold with near-black on-gold ink (`#231a00`), no border.
  One per region. Hover deepens to `#c39a15`. **No press scale** — a button that
  shrinks under the cursor is a toy affordance on a page someone works in for
  eight hours; the colour shift is the feedback.
- **Secondary / Outline / Ghost:** warm neutral fill, 1px border on card, and
  bare respectively — in descending emphasis. Ghost is the toolbar and
  navigation default.
- **Destructive:** solid, reserved for irreversible work.
- **Focus:** 3px `--ring` halo plus a border shift; never removed.

### Chips & Badges

- **Style:** a tinted surface behind a hairline of the same hue, `rounded-md`,
  12px medium label, 2px/8px padding.
- **Status:** semantic tone plus an explicit word and, where available, an icon —
  never color alone.
- **Role:** colored by breadth of authority; hue carries the category and
  lightness carries the ordering, since lightness is the one channel every
  color-vision deficiency preserves.

### Cards / Containers

- **Corner:** 10px (`--radius-card`). **Background:** white on ivory.
- **Border:** 1px `--border`. **Shadow:** `shadow-card` (see Elevation).
- **Padding:** 20px. Group one concept; never nest cards.
- **Heading:** the `title` step (16px/600), ruled off from the body with
  `divided` when the body is a form or a table.

### Inputs / Fields

- **Style:** transparent fill, 1px `--input` border, 6px radius, 36px tall.
- **Focus:** border shifts to `--ring` with a 3px halo.
- **Labels** stay visible above the field; validation sits directly below it in
  `--destructive`. Placeholder text is never a label.

### Tables

- Muted header surface, 12px uppercase micro-caps column labels at 0.06em, 40px
  header row, 1px horizontal rules, and vertical rules between cells so a wide
  row stays readable across the screen. Numbers right-align and run tabular.
  Row hover is a muted wash (`--muted` at 40%).

### Navigation

- Vertical sidebar one step off white with a hairline right border.
- **One answer to "where am I".** The active item takes the sidebar accent
  surface, medium weight, and a `--primary` icon. That is the whole treatment.
  Hover is the *same* surface at 55% — deliberately weaker, because when hover
  and active shared a token, pointing at any row made it look like the page you
  were already on, which is the one thing a rail must never do.
- The gold leading rail is gone. A filled row is the modern signal and the rail
  was a fourth mark for a state that already had three; gold survives here as
  the active icon.
- Subsection headers are built to the nav row's own metrics — same height,
  radius, and inset — so the rail reads as one column at three weights rather
  than a list with a differently-shaped caption wedged into it. They draw a
  connector trunk with a tick per destination, folded away on the icon rail.
- The scroll column fades out over its last 24px, so a long rail says there is
  more below instead of hard-cutting at the footer rule. Where the nav does not
  fill the column the gradient falls over empty space and is invisible.

## Browser Surfaces

The parts of the page nobody draws still carry the design, and left alone they
are the only pixels on screen that came from somewhere else. All of these are
themed in `app.css` and none of them is a component's business:

- **Scrollbar:** 10px, `--border-strong` thumb inset on a transparent track,
  darkening to `--muted-foreground` on hover. Both the Firefox two-value form
  and the WebKit pseudo-elements are stated.
- **Selection:** a 35% gold wash with `--foreground` stated outright — the wash
  sits over ink of two different lightnesses across the themes.
- **Caret:** `--primary`. **Accent-color:** brand gold, so the native date
  picker and any browser-owned control agree with the app.
- **Autofill:** Chrome's wash is overridden with a 1000px inset shadow in
  `--card` and a 10000s transition, the only technique that holds.
- **Markers, placeholders:** `--muted-foreground`.
- **Widows:** `text-wrap: pretty` on `p` and `li`; `text-balance` on headings.
- **Scroll:** smooth (the reduced-motion block already forces it back to auto),
  with `scroll-margin-block` so a focused or targeted element clears the sticky
  header.

**Print.** A brokerage prints — a contract, a report, a roster carried into a
meeting. The rail and the top bar are navigation for a screen and are hidden;
what is left is black on white with the panel rules kept, fills and shadows
dropped, table headers repeated per page, and rows, images, and quotes held off
break boundaries.

**Forced colors.** Windows High Contrast drops background colours, which would
take every border defined as one with it. This app is mostly borders, so cards,
tables, inputs, selects, and badges restate theirs in `CanvasText`.

## Motion

Movement reports a state change and nothing else. One vocabulary:
`--motion-fast` (150ms) for a control answering the pointer, `--motion-base`
(200ms) for something arriving, `--motion-slow` (280ms) for a panel travelling
from an edge, all on `--ease-standard`.

- **Route progress.** An Inertia visit replaces the page without a browser
  navigation, so nothing in the chrome moves and a slow request reads as a dead
  click. One 2px gold sweep rides the header's bottom border while a visit is
  in flight. It is indeterminate and never fills, because the client does not
  know how far along the request is.
- **Reduced motion reduces rather than disables:** colour, border, opacity, and
  shadow keep easing so hover and focus still read as feedback; transforms land
  instantly. The three indeterminate indicators — spinner, pulse, route bar —
  keep looping more slowly, because a stopped progress indicator does not read
  as reduced motion, it reads as hung.

## Do's and Don'ts

### Do:

- **Do** spend gold on actions and brand moments only — the primary button, the
  active navigation icon, the focus ring, the `brand-well` icon tile, the
  sign-in call to action. One button per region, not one per card.
- **Do** declare a tinted surface and its ink as separate tokens, and verify the
  pair at 4.5:1 against its own surface and the card, in both themes.
- **Do** pair every status color with an explicit word, and an icon where one
  exists.
- **Do** let borders carry structure and keep shadow to a single tight contact
  layer; a hairline separates more convincingly than a bloom.
- **Do** reach for a rule before a box. A row of related figures is one ruled
  strip, not four bordered cards.
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
- **Don't** give a container a radius smaller than the thing inside it.
- **Don't** use `rounded-full` on anything that is not a circle.
- **Don't** go below the 11px `micro` step, and don't use it for content.
- **Don't** tint a neutral toward the brand hue to make a surface feel warmer.
  The field is neutral; warmth is gold's job and gold is rationed.
- **Don't** leave a browser surface at its default — a scrollbar, an autofill
  wash, a native picker accent, or a list marker that came from the browser is
  the one thing on the page that was not designed.
- **Don't** animate to make polish visible. Motion answers a state change.
