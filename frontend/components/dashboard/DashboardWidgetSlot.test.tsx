import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { DashboardWidgetSlot } from "@/components/dashboard/DashboardWidgetSlot";
import { PREVIEW_WIDGETS } from "@/lib/dashboard/preview";
import { DASHBOARD_WIDGETS } from "@/lib/dashboard/widget-registry";
import type { DashboardPageProps, DashboardWidget, DashboardWidgetProp } from "@/types";

vi.mock("@inertiajs/react", () => ({
  Deferred: ({ children }: { children: ReactNode }) => children,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { reload: vi.fn() },
}));

function pending(): DashboardWidget<never> {
  return {
    status: "unavailable",
    version: 1,
    generatedAt: "2026-08-20T09:00:00-04:00",
    data: null,
    emptyState: null,
    unavailable: { reason: "Not connected.", retryable: false },
    meta: {},
  };
}

function page(): DashboardPageProps {
  const widgets: Partial<Record<DashboardWidgetProp, DashboardWidget<never>>> = {};
  for (const widget of DASHBOARD_WIDGETS) {
    if (widget.backed) {
      widgets[widget.prop] = pending();
    }
  }
  return {
    user: null,
    csrfToken: "token",
    requestId: "request-1",
    features: {},
    primaryOffice: null,
    shell: {
      authorizationVersion: "access-v1",
      capabilitySchemaVersion: "p0-permissions-v1",
      help: { url: null },
      session: { authenticated: true },
    },
    greeting: {
      salutation: "Good morning",
      name: "Reader",
      dateLabel: "Thursday, August 20",
      dateIso: "2026-08-20",
      timezone: "America/New_York",
    },
    ...widgets,
  };
}

describe("DashboardWidgetSlot", () => {
  // The switch in the slot is the id → component allowlist. A registered id
  // with no case there is a panel that silently disappears from every profile
  // that lists it, which no other test would notice.
  it.each(DASHBOARD_WIDGETS.map((widget) => widget.id))("renders %s", (id) => {
    const definition = DASHBOARD_WIDGETS.find((widget) => widget.id === id);
    if (!definition) {
      throw new Error(`${id} is not registered`);
    }
    const { container } = render(
      <DashboardWidgetSlot
        resolved={{ definition, withheld: false }}
        page={page()}
        stale={false}
      />,
    );
    expect(container).not.toBeEmptyDOMElement();
  });

  it("gives every unbacked widget a preview payload to render", () => {
    // Without one, the slot renders nothing at all — worse than a panel that
    // says it has no data.
    for (const widget of DASHBOARD_WIDGETS) {
      if (!widget.backed) {
        expect(
          Object.hasOwn(PREVIEW_WIDGETS, widget.id),
          `${widget.id} is unbacked and has no preview fixture`,
        ).toBe(true);
      }
    }
  });

  it("renders a restricted placeholder instead of the widget when withheld", () => {
    const definition = DASHBOARD_WIDGETS.find(
      (widget) => widget.deniedBehavior === "withhold",
    );
    if (!definition) {
      throw new Error("no widget uses the withhold behavior");
    }
    const { getByRole } = render(
      <DashboardWidgetSlot
        resolved={{ definition, withheld: true }}
        page={page()}
        stale={false}
      />,
    );
    expect(getByRole("heading", { name: "Restricted" })).toBeVisible();
  });
});
