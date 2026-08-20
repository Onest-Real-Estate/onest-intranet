import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";

import { QuickApps } from "@/components/dashboard/QuickApps";
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

  it("opens an external tool in a new tab and says so", () => {
    render(<QuickApps apps={[app()]} />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
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
    expect(link.textContent).not.toContain("opens in a new tab");
  });

  it("flags a degraded integration in words, not colour alone", () => {
    render(<QuickApps apps={[app({ health: "offline" })]} />);
    expect(screen.getByText("Offline")).toBeVisible();
  });

  it("falls back to a generic mark for an icon the bundle does not know", () => {
    const { container } = render(<QuickApps apps={[app({ icon: "not-a-mark" })]} />);
    expect(container.querySelector("svg")).not.toBeNull();
    expect(screen.getByRole("link").textContent).toContain("Lofty");
  });

  it("has no detectable accessibility violations", async () => {
    const { container } = render(
      <QuickApps apps={[app(), app({ id: "internal", external: false })]} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
