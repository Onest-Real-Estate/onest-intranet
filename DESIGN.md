---
name: oNEST Core
colors:
  surface: '#fbf9f3'
  surface-dim: '#dbdad4'
  surface-bright: '#fbf9f3'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f5f4ed'
  surface-container: '#efeee8'
  surface-container-high: '#eae8e2'
  surface-container-highest: '#e4e2dc'
  on-surface: '#1b1c18'
  on-surface-variant: '#4d4634'
  inverse-surface: '#30312d'
  inverse-on-surface: '#f2f1ea'
  outline: '#7f7662'
  outline-variant: '#d0c6ae'
  surface-tint: '#735c00'
  primary: '#735c00'
  on-primary: '#ffffff'
  primary-container: '#ddb52a'
  on-primary-container: '#5a4700'
  inverse-primary: '#ebc238'
  secondary: '#5f5e5e'
  on-secondary: '#ffffff'
  secondary-container: '#e2dfde'
  on-secondary-container: '#636262'
  tertiary: '#5e5f5c'
  on-tertiary: '#ffffff'
  tertiary-container: '#b9b9b6'
  on-tertiary-container: '#494a47'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ffe087'
  primary-fixed-dim: '#ebc238'
  on-primary-fixed: '#231a00'
  on-primary-fixed-variant: '#574500'
  secondary-fixed: '#e5e2e1'
  secondary-fixed-dim: '#c8c6c5'
  on-secondary-fixed: '#1c1b1b'
  on-secondary-fixed-variant: '#474746'
  tertiary-fixed: '#e3e2df'
  tertiary-fixed-dim: '#c7c7c3'
  on-tertiary-fixed: '#1b1c1a'
  on-tertiary-fixed-variant: '#464744'
  background: '#fbf9f3'
  on-background: '#1b1c18'
  surface-variant: '#e4e2dc'
typography:
  display:
    fontFamily: Plus Jakarta Sans
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: '0'
  body-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: '0'
  body-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: '0'
  label-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.02em
  headline-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 36px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 8px
  xs: 4px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
  xxl: 48px
  margin-mobile: 16px
  margin-desktop: 40px
  gutter: 24px
---

## Brand & Style
The design system is a premium, agent-centric framework that balances the precision of high-end SaaS with the warmth of luxury real estate. The aesthetic is **Modern Minimalist with Tactile Refinement**, prioritizing clarity, focus, and a "surgical" application of brand elements.

The UI should evoke a sense of quiet confidence and professional mastery. By utilizing expansive white space and a sophisticated neutral palette, the design system ensures that agent data and property imagery remain the focal point. Interaction models are inspired by high-performance tools like Linear—fast, keyboard-accessible, and devoid of unnecessary visual noise.

## Colors
This design system utilizes a palette of warm neutrals and high-contrast accents to create a premium atmosphere.

- **oNEST Gold (#DDB52A):** Used sparingly for primary actions, focus states, and critical brand touchpoints. It should never overwhelm the layout.
- **Warm Ivory Background (#F8F7F3):** The primary canvas. This off-white tone reduces eye strain and provides a softer, more sophisticated feel than pure white.
- **Deep Charcoal & Near Black:** Used for typography to ensure maximum legibility and a sense of authority. 
- **Soft Warm Border (#E9E6DE):** Defines structure without creating harsh visual barriers.

## Typography
The typography system uses **Plus Jakarta Sans** for its modern, clean, yet approachable geometric forms. 

Headings are restrained in size but confident in weight (Bold/600-700), creating a clear hierarchy. Body text is optimized for long-form readability with generous line heights. Labels use a slightly tighter tracking and semi-bold weight to distinguish metadata from content. For mobile views, heading sizes scale down to maintain a balanced information density.

## Layout & Spacing
The layout relies on an **8px linear grid system** to ensure mathematical harmony across all components.

- **Desktop:** A 12-column fluid grid with 40px outer margins and 24px gutters. Content is typically capped at a 1440px max-width to maintain readability.
- **Tablet:** 8-column grid with 24px margins.
- **Mobile:** 4-column grid with 16px margins.

Spacing is generous ("Airy") to prevent the portal from feeling like a crowded administrative tool. Use `xl` (32px) or `xxl` (48px) padding for section containers to emphasize the premium nature of the interface.

## Elevation & Depth
This design system uses a **Tonal Layering** approach combined with extremely soft, ambient shadows.

- **Level 0 (Base):** Warm Ivory (#F8F7F3). All page backgrounds.
- **Level 1 (Surface):** White (#FFFFFF) cards. These use a 1px border (#E9E6DE) and a very diffuse shadow: `0 4px 12px rgba(23, 23, 23, 0.03)`.
- **Level 2 (Interaction/Popovers):** White (#FFFFFF) with a more defined shadow to suggest proximity: `0 8px 24px rgba(23, 23, 23, 0.08)`.

Avoid heavy dropshadows or generic "box-shadow" presets. The goal is to make elements appear to rest gently on the warm background, rather than floating far above it.

## Shapes
The shape language is consistently "Rounded" to reflect a friendly yet professional persona. 

- **Cards & Major Containers:** 14px (rounded-lg) corner radius.
- **Buttons & Inputs:** 8px (standard) corner radius.
- **Tags/Chips:** Fully rounded (pill) to distinguish them from interactive buttons.

This consistent use of softened corners removes the "industrial" feel common in enterprise software, aligning the portal with modern lifestyle and SaaS aesthetics.

## Components

### Buttons
- **Primary:** oNEST Gold background, Near Black (#0D0D0D) text. No border. High contrast, immediate visibility.
- **Secondary:** White background, 1px Soft Warm Border (#E9E6DE), Deep Charcoal text.
- **Ghost:** No background or border. Text only (Deep Charcoal or Muted Text). Used for secondary actions in headers.

### Input Fields
- White background, 1px border (#E9E6DE), 8px radius.
- Focus state: Border changes to oNEST Gold (#DDB52A) with a 2px outer "glow" using the Soft Gold Tint (#FBF5DF).
- Placeholder text uses Muted Text (#7A7A75).

### Cards
- The foundational component for property listings and agent metrics. 
- Always White (#FFFFFF) with a 14px radius and a subtle border.
- Padding should be 24px (lg) to maintain the "premium" feel.

### Chips & Badges
- Used for property status (e.g., "Active", "Sold").
- Light tinted backgrounds (e.g., Soft Gold Tint) with dark text. 
- Pill-shaped with a 12px Label-MD font.

### Icons
- **Style:** Lucide-inspired thin strokes (1.5px or 2px weight).
- **Color:** Deep Charcoal for active icons, Muted Text for inactive/decorative icons.

### Additional Elements
- **Navigation:** Vertical side-bar with a subtle hairline border on the right. Active states use a small vertical oNEST Gold bar (4px wide) on the far left of the menu item.
- **Data Tables:** Row-based with no vertical dividers. Use 1px horizontal lines (#E9E6DE). Hover state for rows uses the Soft Gold Tint (#FBF5DF).