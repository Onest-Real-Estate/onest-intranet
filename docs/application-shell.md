# Application shell

Every authenticated, onboarded Inertia page uses `HubLayout`. The shell owns
the desktop rail, mobile drawer, page context, global entry points, account
menu, route loading state, and the three supported content widths. Pages own
their `Head`, `h1`, and product content.

## Page contract

Declare the persistent layout with Inertia's layout callback. The callback
keeps layout choices beside the page and lets dynamic pages use their own
props without sending presentation markup from Django.

```tsx
Reports.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Reports",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Reports" },
        ],
        back: { label: "Back to dashboard", href: routes.dashboard() },
      },
      variant: "standard",
    },
  ] as const;
```

Use `standard` for ordinary product pages, `wide` for data-heavy grids, and
`focused` for forms, errors, and single-task flows. The shell supplies the
responsive gutters and maximum width; a page must not add a second outer
`page-shell`.

`context.title` is the compact header label, not the page `h1`. Breadcrumb and
back destinations must come from the generated `routes` map. The shell rejects
non-local back destinations and falls back to the dashboard. If `context` is
omitted, the shell derives the title from the active navigation item; deep
links that do not match the registry should always declare context.

## Shared props

`InertiaShareMiddleware` provides only current-user shell data:

- approved identity fields and the effective permission union;
- the current user's small office summary;
- permission-filtered feature availability;
- an opaque authorization version that changes with permissions or scope;
- a backend-validated HTTPS help URL, when configured;
- authenticated session state and the CSRF token.

Navigation is resolved from `HUB_NAV_REGISTRY` only after those props arrive,
so the server response never hydrates an unauthorized destination. Route
authorization remains mandatory; shell filtering is not a security boundary.

Set `HUB_HELP_URL` to an absolute HTTPS URL to enable the help entry point.
Empty, relative, non-HTTPS, and credential-bearing values fail closed.

## Navigation and failure behavior

The mobile drawer uses the same filtered registry as the desktop rail and
closes on every Inertia visit. The drawer traps focus and restores it when
closed; successful visits then focus the content region without changing its
scroll position. The content region exposes `aria-busy`, and the global route
progress uses the semantic primary token with reduced-motion support.

Network and server failures keep the current page visible and offer a fresh
retry. Authentication failures offer sign-in again. Render and chunk-loading
errors fall through to the application error boundary. Real 403 and 404
responses continue to use their dedicated Inertia pages.
