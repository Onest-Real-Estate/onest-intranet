import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { QuickApps } from "@/components/dashboard/QuickApps";
import { QUICK_ACCESS_COLLAPSED_LIMIT } from "@/lib/quick-access";
import type { DashboardQuickApp } from "@/types";

function app(overrides: Partial<DashboardQuickApp> = {}): DashboardQuickApp {
  return {
    id: "lofty",
    name: "Lofty",
    description: "Where leads live",
    href: "https://www.lofty.com",
    icon: "contact",
    external: true,
    sso: "none",
    health: "unknown",
    setup: "self_service",
    ...overrides,
  };
}

function manyApps(count: number): DashboardQuickApp[] {
  return Array.from({ length: count }, (_unused, index) =>
    app({ id: `tool-${index}`, name: `Tool ${index}` }),
  );
}

describe("QuickApps", () => {
  it("renders the launchers the server resolved, in the order it sent them", () => {
    render(
      <QuickApps
        apps={[app(), app({ id: "skyslope", name: "SkySlope", icon: "shield-check" })]}
      />,
    );
    const links = screen.getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual([
      expect.stringContaining("Lofty"),
      expect.stringContaining("SkySlope"),
    ]);
  });

  it("opens an external tool in a new tab, with the opener and referrer withheld", () => {
    render(<QuickApps apps={[app()]} />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link.textContent).toContain("opens in a new tab");
  });

  it("navigates in place for an internal destination", () => {
    render(
      <QuickApps
        apps={[
          app({
            id: "office-info",
            name: "Office info",
            href: "/hub/office-info",
            external: false,
          }),
        ]}
      />,
    );
    const link = screen.getByRole("link");
    expect(link).not.toHaveAttribute("target");
    expect(link).not.toHaveAttribute("rel");
    expect(link.textContent).not.toContain("opens in a new tab");
  });

  it("falls back to a generic mark for an icon the bundle does not know", () => {
    const { container } = render(<QuickApps apps={[app({ icon: "not-a-mark" })]} />);
    expect(container.querySelector("svg")).not.toBeNull();
    expect(screen.getByRole("link").textContent).toContain("Lofty");
  });

  it("says the payload was capped when the server truncated it", () => {
    render(<QuickApps apps={[app()]} truncated />);
    expect(screen.getByText(/Ask an administrator if one is missing/)).toBeVisible();
  });

  it("says nothing about a cap when the server sent everything", () => {
    render(<QuickApps apps={[app()]} />);
    expect(screen.queryByText(/Ask an administrator if one is missing/)).toBeNull();
  });
});

// --------------------------------------------------------------------------- //
// States
// --------------------------------------------------------------------------- //

describe("QuickApps states", () => {
  it("flags a degraded integration in words, not colour alone", () => {
    render(<QuickApps apps={[app({ health: "degraded" })]} />);
    expect(screen.getByText(/Degraded/)).toBeVisible();
    // Still a launcher: degraded means slow, not gone.
    expect(screen.getByRole("link")).toHaveAttribute("data-state", "degraded");
  });

  it("does not render an offline integration as a link at all", () => {
    render(<QuickApps apps={[app({ health: "offline" })]} />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText(/Unavailable/)).toBeVisible();
    expect(screen.getByText(/cannot be opened right now/)).toBeInTheDocument();
  });

  it("says a tool needs access requested before it works", () => {
    render(<QuickApps apps={[app({ setup: "request_access" })]} />);
    expect(screen.getByText(/Setup required/)).toBeVisible();
    expect(screen.getByRole("link")).toHaveAttribute("data-state", "setup");
  });

  it("shows the description, not a state, for a healthy self-service tool", () => {
    render(<QuickApps apps={[app({ health: "healthy" })]} />);
    expect(screen.getByText("Where leads live")).toBeVisible();
    expect(screen.getByRole("link")).toHaveAttribute("data-state", "ready");
  });

  it("keeps the three states apart when one link is offline and one degraded", () => {
    render(
      <QuickApps
        apps={[
          app({ id: "down", name: "Down", health: "offline" }),
          app({ id: "slow", name: "Slow", health: "degraded" }),
          app({ id: "new", name: "New", setup: "request_access" }),
        ]}
      />,
    );
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).queryByRole("link")).toBeNull();
    expect(within(rows[1]).getByRole("link")).toHaveAttribute("data-state", "degraded");
    expect(within(rows[2]).getByRole("link")).toHaveAttribute("data-state", "setup");
  });

  it("health outranks setup: an offline tool is not offered as a setup step", () => {
    render(<QuickApps apps={[app({ health: "offline", setup: "request_access" })]} />);
    expect(screen.queryByText(/Setup required/)).toBeNull();
    expect(screen.getByText(/Unavailable/)).toBeVisible();
  });
});

// --------------------------------------------------------------------------- //
// Maximum and "View all"
// --------------------------------------------------------------------------- //

describe("QuickApps overflow", () => {
  it("shows every launcher when the panel is under its maximum", () => {
    render(<QuickApps apps={manyApps(QUICK_ACCESS_COLLAPSED_LIMIT)} />);
    expect(screen.getAllByRole("link")).toHaveLength(QUICK_ACCESS_COLLAPSED_LIMIT);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("collapses past the maximum and offers to show the rest", async () => {
    const user = userEvent.setup();
    render(<QuickApps apps={manyApps(QUICK_ACCESS_COLLAPSED_LIMIT + 3)} />);

    expect(screen.getAllByRole("link")).toHaveLength(QUICK_ACCESS_COLLAPSED_LIMIT);
    const toggle = screen.getByRole("button", {
      name: `View all ${QUICK_ACCESS_COLLAPSED_LIMIT + 3} tools`,
    });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await user.click(toggle);
    expect(screen.getAllByRole("link")).toHaveLength(QUICK_ACCESS_COLLAPSED_LIMIT + 3);
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    await user.click(screen.getByRole("button", { name: "Show fewer tools" }));
    expect(screen.getAllByRole("link")).toHaveLength(QUICK_ACCESS_COLLAPSED_LIMIT);
  });

  it("expands from the keyboard", async () => {
    const user = userEvent.setup();
    render(<QuickApps apps={manyApps(QUICK_ACCESS_COLLAPSED_LIMIT + 1)} />);
    const toggle = screen.getByRole("button");
    toggle.focus();
    await user.keyboard("{Enter}");
    expect(screen.getAllByRole("link")).toHaveLength(QUICK_ACCESS_COLLAPSED_LIMIT + 1);
  });

  it("points the toggle at the list it controls", () => {
    render(<QuickApps apps={manyApps(QUICK_ACCESS_COLLAPSED_LIMIT + 1)} />);
    const controls = screen.getByRole("button").getAttribute("aria-controls");
    expect(controls).toBeTruthy();
    expect(screen.getByRole("list").id).toBe(controls);
  });
});

// --------------------------------------------------------------------------- //
// Click analytics
// --------------------------------------------------------------------------- //

describe("QuickApps click analytics", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reports the click by stable key, and never the destination", async () => {
    const user = userEvent.setup();
    render(<QuickApps apps={[app()]} csrfToken="token" />);
    await user.click(screen.getByRole("link"));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/dashboard/quick-access/click");
    expect(init.keepalive).toBe(true);
    const body = init.body as FormData;
    expect(body.get("key")).toBe("lofty");
    expect(body.get("csrfmiddlewaretoken")).toBe("token");
    // The URL is the one thing that can carry a third-party token.
    expect([...body.values()].join(" ")).not.toContain("lofty.com");
  });

  it("does not report a click on a row that is not a launcher", async () => {
    const user = userEvent.setup();
    render(<QuickApps apps={[app({ health: "offline" })]} csrfToken="token" />);
    await user.click(screen.getByText("Lofty"));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("navigates even when the beacon rejects", async () => {
    fetchMock.mockImplementation(() => Promise.reject(new Error("offline")));
    const user = userEvent.setup();
    render(<QuickApps apps={[app()]} csrfToken="token" />);
    // An unhandled rejection here would fail the run; the helper swallows it.
    await user.click(screen.getByRole("link"));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

// --------------------------------------------------------------------------- //
// Accessibility
// --------------------------------------------------------------------------- //

describe("QuickApps accessibility", () => {
  it("has no detectable violations across every state", async () => {
    const { container } = render(
      <QuickApps
        apps={[
          app(),
          app({ id: "internal", external: false }),
          app({ id: "down", health: "offline" }),
          app({ id: "slow", health: "degraded" }),
          app({ id: "setup", setup: "request_access" }),
        ]}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("keeps a very long name inside the row", () => {
    render(<QuickApps apps={[app({ name: "A".repeat(120) })]} />);
    const name = screen.getByText("A".repeat(120));
    expect(name.className).toContain("line-clamp-2");
    expect(name.className).toContain("break-words");
  });
});

describe("vendor marks", () => {
  it("draws a vendor's own artwork instead of a category glyph", () => {
    // Lofty ships as an image mark; the generic Lucide fallback must not also
    // render, or the tile would carry two icons.
    const { container } = render(
      <QuickApps apps={[app({ id: "lofty", name: "Lofty", icon: "lofty" })]} />,
    );
    // Scoped to the tile: the row also carries a Lucide chevron of its own.
    expect(container.querySelector(".brand-well img")).not.toBeNull();
    expect(container.querySelector(".brand-well svg")).toBeNull();
  });

  it("lets a mark that carries its own background be the tile", () => {
    // RPR's artwork is a black rounded tile. Nesting it inside the gold well
    // would put two squares inside each other.
    const { container } = render(
      <QuickApps apps={[app({ id: "rpr", name: "RPR", icon: "rpr" })]} />,
    );
    expect(container.querySelector(".brand-well")).toBeNull();
    expect(container.querySelector("img")).not.toBeNull();
  });

  it("still draws the approved glyph for a vendor with no shipped artwork", () => {
    const { container } = render(
      <QuickApps apps={[app({ id: "other", name: "Other", icon: "wallet" })]} />,
    );
    expect(container.querySelector(".brand-well img")).toBeNull();
    expect(container.querySelector(".brand-well svg")).not.toBeNull();
  });
});
