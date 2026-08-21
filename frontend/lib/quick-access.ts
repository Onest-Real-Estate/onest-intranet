import { routes } from "@/lib/routes";
import type { DashboardQuickApp } from "@/types";

/**
 * How many launchers the panel shows before it offers "View all".
 *
 * The panel occupies the narrow third of the dashboard's top band, so this is
 * a layout decision rather than a data one: six rows is the most that fits
 * beside the news band without the card outgrowing its neighbours. The server
 * sends up to the registry's `feed_limit`; everything past this number is one
 * button away, never dropped.
 */
export const QUICK_ACCESS_COLLAPSED_LIMIT = 6;

/**
 * What the panel says about a launcher, beyond its name.
 *
 * Four outcomes, kept apart because conflating any two of them misleads the
 * reader about whether clicking will work:
 *
 * - `ready` — open it.
 * - `setup` — the tool exists but access has to be requested first.
 * - `degraded` — reachable, but the integration is misbehaving.
 * - `unavailable` — the integration is offline. The row is not a link at all;
 *   a launcher that cannot launch should not look like one.
 *
 * Health outranks setup: there is nothing to set up on a tool that is down.
 */
export type QuickAppState = "ready" | "setup" | "degraded" | "unavailable";

export interface QuickAppStatus {
  state: QuickAppState;
  /** Rendered as the row's second line. Empty for `ready`. */
  label: string;
  /** Read to assistive technology in place of a colour cue. */
  announcement: string;
}

const STATUS: Record<Exclude<QuickAppState, "ready">, Omit<QuickAppStatus, "state">> = {
  unavailable: {
    label: "Unavailable — integration offline",
    announcement: "Integration status: offline. This tool cannot be opened right now.",
  },
  degraded: {
    label: "Degraded — may be slow or partly unavailable",
    announcement: "Integration status: degraded.",
  },
  setup: {
    label: "Setup required — request access first",
    announcement: "Setup status: access must be requested before this tool works.",
  },
};

export function quickAppStatus(app: DashboardQuickApp): QuickAppStatus {
  if (app.health === "offline") {
    return { state: "unavailable", ...STATUS.unavailable };
  }
  if (app.health === "degraded") {
    return { state: "degraded", ...STATUS.degraded };
  }
  if (app.setup === "request_access") {
    return { state: "setup", ...STATUS.setup };
  }
  return { state: "ready", label: "", announcement: "" };
}

/**
 * Tell the server a launcher was opened, without making the reader wait.
 *
 * `keepalive` is the whole point: the request outlives the page that started
 * it, so the browser can follow the link immediately and the count still
 * arrives. Every failure is swallowed — a lost count must never surface as an
 * error beside a link that opened perfectly well.
 *
 * Only the link's stable key is sent. The destination, and therefore anything
 * an external tool might carry in its query string, never leaves the page.
 */
export function reportQuickAppClick(app: DashboardQuickApp, csrfToken: string): void {
  if (typeof fetch !== "function") {
    return;
  }
  const body = new FormData();
  body.append("key", app.id);
  body.append("csrfmiddlewaretoken", csrfToken);
  try {
    void fetch(routes.quick_access_click(), {
      method: "POST",
      body,
      keepalive: true,
      credentials: "same-origin",
    }).catch(() => {});
  } catch {
    // A browser that refuses the beacon outright still gets to navigate.
  }
}
