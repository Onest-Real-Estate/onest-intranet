# Onest intranet design system

This system translates the gold house-and-key logo into an accessible, practical interface for daily internal use. The logo's sampled gold, `#B6852E`, is the signature color; semantic UI tokens use contrast-adjusted variants where needed.

## Principles

1. **Clear before decorative.** Dense operational information should remain easy to scan.
2. **Warm and trustworthy.** Gold and warm neutrals distinguish Onest without making every surface feel promotional.
3. **Accessible by default.** Never rely on color alone; pair status color with text or an icon and preserve visible keyboard focus.
4. **Consistent over custom.** Product work should use semantic shadcn tokens, not one-off hex values.

## Color

| Role | Light reference | Use |
| --- | --- | --- |
| Brand gold | `#B6852E` | Logo, small highlights, decorative details |
| Primary | `oklch(0.50 0.115 74)` | Primary actions, active navigation, links |
| Background | `oklch(0.985 0.006 80)` | App canvas |
| Foreground | `oklch(0.22 0.018 72)` | Main text |
| Card | `#FFFFFF` | Raised content surfaces |
| Muted | `oklch(0.96 0.008 78)` | Secondary surfaces and table headers |
| Destructive | `oklch(0.56 0.20 27)` | Errors and irreversible actions |
| Success | `oklch(0.49 0.12 150)` | Completed and healthy states |
| Warning | `oklch(0.68 0.14 70)` | Attention-needed states |
| Info | `oklch(0.52 0.13 245)` | Neutral notices and guidance |

Use `bg-primary`, `text-muted-foreground`, `border-border`, and the other semantic utilities exposed in `frontend/css/app.css`. Use `brand-text` and `brand-surface` only for brand expression—not general UI state. The `.dark` class switches the complete token set, including charts and sidebar colors.

## Typography

The preferred UI face is **Plus Jakarta Sans** (self-hosted variable cut), falling back to the platform sans-serif. Headings use 600–700 weight with tight tracking; labels use 600 with slightly open tracking, matching `DESIGN.md`.

| Style | Tailwind recipe | Typical use |
| --- | --- | --- |
| Display | `text-[40px] font-bold leading-12 tracking-[-0.02em]` | Rare hero copy |
| Page title | `text-[32px] font-bold leading-10 tracking-[-0.02em]` | One per page |
| Section title | `text-xl font-semibold tracking-tight` | Major page sections |
| Card title | `font-semibold leading-none` | Card headings |
| Body | `text-sm` or `text-base leading-6` | Interface and long-form copy |
| Supporting | `text-sm text-muted-foreground` | Descriptions and metadata |
| Label | `text-xs font-semibold tracking-[0.02em]` | Form and data labels |

Use sentence case. Reserve all caps for the compact ONEST wordmark. Keep paragraphs near 65 characters per line when possible.

## Spacing and layout

Use Tailwind's 4 px spacing scale. The default gaps are 8 px for tightly related controls, 16 px for component content, 24 px between sections, and 40–64 px for page-level separation. Use the shared `page-shell` utility for application pages; it provides a `max-w-6xl` centered container and responsive gutters.

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
- **Tables:** right-align numbers, keep headers concise, and use a muted header surface. On narrow screens, prioritize or stack columns rather than shrinking text below 14 px.
- **Navigation:** keep the primary nav stable. Active items use the accent surface and should also expose `aria-current="page"`.

All interactive controls need a visible focus ring, a minimum practical target of 36 px (44 px on touch-heavy screens), a disabled state, and clear hover/pressed feedback. Animations should generally stay between 120–200 ms and respect reduced-motion preferences.

## Icons and imagery

Use Lucide icons at 16–20 px with a consistent 1.5 px stroke (`LucideProvider` in `frontend/main.tsx`). Active icons are deep charcoal; inactive or decorative icons use muted text. Pair icons with labels; they do not replace uncommon action labels. Use the compact `BrandMark` component in product chrome and the supplied full logo only in brand/marketing contexts where its detail remains legible.

## Implementation checklist

- Choose semantic tokens rather than raw palette values.
- Check light and `.dark` themes.
- Check keyboard focus and logical tab order.
- Verify empty, loading, error, disabled, and success states.
- Test at 320 px, 768 px, and a desktop width.
- Confirm text/background contrast and never encode status with color alone.
