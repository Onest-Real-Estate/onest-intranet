import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

const pageProps = vi.hoisted(() => ({ current: {} as TeamToolReadinessPageProps }));
const routerGet = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/operations/tool-readiness" }),
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  Head: () => null,
  router: { get: routerGet },
}));

import TeamToolReadiness from "@/pages/TeamToolReadiness";
import type { TeamToolReadinessPageProps } from "@/types";

function setPage(overrides: Partial<TeamToolReadinessPageProps> = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "lead@onest.realestate",
      name: "Branch Lead",
      headshotUrl: null,
      permissions: ["web.view_new_agents"],
      roles: ["branch_manager"],
      roleLabel: "Branch manager",
      isStaff: false,
      isSuperuser: false,
    },
    csrfToken: "token",
    requestId: "r1",
    features: {},
    primaryOffice: null,
    shell: null,
    notifications: null,
    filters: { q: "" },
    agents: [
      {
        id: 2,
        name: "Ada Newcomer",
        office: "Connecticut",
        ready: 3,
        total: 21,
        percent: 14,
        complete: false,
      },
      {
        id: 3,
        name: "Bo Settled",
        office: "Fairfax VA",
        ready: 17,
        total: 17,
        percent: 100,
        complete: true,
      },
    ],
    errors: { fields: {}, form: [] },
    ...overrides,
  } as TeamToolReadinessPageProps;
}

beforeEach(() => {
  routerGet.mockClear();
  setPage();
});

describe("TeamToolReadiness", () => {
  it("shows each agent's office and how far they have got", () => {
    render(<TeamToolReadiness />);
    expect(screen.getByText("Ada Newcomer")).toBeVisible();
    expect(screen.getByText("Connecticut")).toBeVisible();
    expect(screen.getByText("3 of 21")).toBeVisible();
  });

  it("says who is finished in words, not only in colour", () => {
    render(<TeamToolReadiness />);
    expect(screen.getByText("Ready")).toBeVisible();
  });

  it("counts who is still outstanding", () => {
    render(<TeamToolReadiness />);
    expect(screen.getByText("1 still setting up")).toBeVisible();
  });

  it("gives every bar an accessible name naming the person", () => {
    render(<TeamToolReadiness />);
    // A row of unlabelled bars tells a screen-reader user nothing about whose
    // progress they are hearing.
    const bar = screen.getByRole("progressbar", { name: /Ada Newcomer/ });
    expect(bar).toHaveAttribute("aria-valuenow", "14");
  });

  it("links each agent to their own checklist", () => {
    render(<TeamToolReadiness />);
    const link = screen.getByRole("link", { name: /Ada Newcomer/ });
    expect(link).toHaveAttribute("href", "/operations/tool-readiness/2");
  });

  it("searches server-side so the scope filter still applies", async () => {
    const user = userEvent.setup();
    render(<TeamToolReadiness />);

    const box = screen.getByLabelText("Search agents");
    await user.type(box, "ada{Enter}");

    // The control may fire while typing; what matters is that the term
    // reached the server, which is where the scope filter lives.
    const withTerm = routerGet.mock.calls.find(
      (call) => (call[1] as { q?: string })?.q === "ada",
    );
    expect(withTerm).toBeDefined();
    expect(withTerm?.[0]).toBe("/operations/tool-readiness");
  });

  it("distinguishes an empty search from an empty team", () => {
    setPage({ agents: [], filters: { q: "zzz" } });
    render(<TeamToolReadiness />);
    expect(screen.getByText("No agent matches that")).toBeVisible();

    setPage({ agents: [], filters: { q: "" } });
    render(<TeamToolReadiness />);
    expect(screen.getByText("Nobody to show")).toBeVisible();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<TeamToolReadiness />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
