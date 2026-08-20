import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import NewAgentList from "@/pages/NewAgentList";
import type { NewAgentListPageProps } from "@/types";

const pageProps = vi.hoisted(() => ({ current: {} as NewAgentListPageProps }));
const routerGet = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({
    props: pageProps.current,
    url: "/operations/new-agents",
  }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: routerGet },
}));

function setPage(
  items = [
    {
      user: {
        id: 9,
        name: "Bob Lee",
        email: "bob@onest.realestate",
        office: "Fairfax VA",
        region: "Mid-Atlantic",
        startDate: "2026-08-25",
        isActive: true,
      },
      owner: { id: 1, name: "Ada Admin" },
      overallStatus: "blocked",
      overall: { value: "blocked", label: "Blocked", tone: "destructive" as const },
      blockers: [{ key: "required_training", label: "Training source unavailable" }],
      progress: { complete: 2, total: 10 },
      contractStatus: "unavailable",
      contract: {
        value: "unavailable",
        label: "Source unavailable",
        tone: "neutral" as const,
      },
      trainingStatus: "unavailable",
      training: {
        value: "unavailable",
        label: "Source unavailable",
        tone: "neutral" as const,
      },
      openTaskCount: 1,
      version: "",
      lastChangedAt: null,
      lastChangedBy: null,
    },
  ],
) {
  pageProps.current = {
    user: {
      id: 1,
      email: "ada@onest.realestate",
      name: "Ada Admin",
      headshotUrl: null,
      permissions: ["web.view_new_agents", "web.manage_new_agent_onboarding"],
      roles: ["System Admin"],
      roleLabel: "System Admin",
      isStaff: false,
      isSuperuser: false,
    },
    csrfToken: "token",
    requestId: "00000000-0000-4000-8000-000000000001",
    features: {},
    primaryOffice: null,
    shell: {
      authorizationVersion: "v1",
      capabilitySchemaVersion: "p0-permissions-v1",
      help: { url: null },
      session: { authenticated: true },
    },
    agents: {
      items,
      pagination: {
        page: 1,
        pageSize: 25,
        totalItems: items.length,
        totalPages: 1,
        hasNext: false,
        hasPrevious: false,
      },
      filters: {
        q: "",
        office: "",
        owner: "",
        blocker: "",
        overallStatus: "",
        startFrom: "",
        startTo: "",
        contractStatus: "",
        trainingStatus: "",
      },
      sort: { key: "startDate", direction: "desc" },
    },
    filterOptions: {
      offices: [{ value: "7", label: "Mid-Atlantic / Fairfax VA" }],
      owners: [{ value: "1", label: "Ada Admin" }],
      blockers: [{ value: "any", label: "Any blocker" }],
      overallStatuses: [{ value: "blocked", label: "Blocked" }],
      sourceStatuses: [{ value: "unavailable", label: "Source unavailable" }],
    },
    scopeLabel: "Brokerage-wide",
  };
}

beforeEach(() => {
  routerGet.mockClear();
  setPage();
  window.history.replaceState({}, "", "/operations/new-agents");
});

describe("NewAgentList", () => {
  it("renders source-derived progress and the permitted detail destination", () => {
    render(<NewAgentList />);
    const row = screen
      .getAllByRole("row")
      .find((candidate) => candidate.textContent?.includes("Bob Lee"));
    expect(row).toBeDefined();
    expect(within(row as HTMLElement).getByText("Blocked")).toBeVisible();
    expect(within(row as HTMLElement).getByText("2 of 10")).toBeVisible();
    expect(
      within(row as HTMLElement).getByRole("link", { name: /review/i }),
    ).toHaveAttribute("href", "/operations/new-agents/9");
  });

  it("delegates filtering to the scoped server list", async () => {
    const user = userEvent.setup();
    render(<NewAgentList />);
    await user.click(screen.getByRole("combobox", { name: "Status" }));
    await user.click(screen.getByRole("option", { name: "Blocked" }));
    expect(routerGet).toHaveBeenCalledWith(
      expect.stringContaining("overallStatus=blocked"),
      {},
      expect.anything(),
    );
  });

  it("shows an actionable no-result state", () => {
    setPage([]);
    render(<NewAgentList />);
    expect(screen.getByText(/No onboarding records match/i)).toBeVisible();
    expect(screen.getByText(/Reset filters or check the office/i)).toBeVisible();
  });

  it("has no detectable accessibility violations", async () => {
    const { container } = render(<NewAgentList />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
