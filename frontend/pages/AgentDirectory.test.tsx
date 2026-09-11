import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import AgentDirectory from "@/pages/AgentDirectory";
import type { AgentDirectoryPageProps, AgentDirectoryPerson } from "@/types";

const pageProps = vi.hoisted(() => ({ current: {} as AgentDirectoryPageProps }));
const routerGet = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/hub/agent-directory" }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: routerGet },
}));

const person: AgentDirectoryPerson = {
  id: 42,
  preferredName: "Ada Agent",
  roles: ["Realtor"],
  office: {
    id: 7,
    name: "Fairfax VA",
    pathLabel: "Mid-Atlantic / Fairfax VA",
    regionName: "Mid-Atlantic",
  },
  workPhone: "(703) 555-0100",
  workEmail: "ada@onest.realestate",
  specialties: [{ code: "residential", name: "Residential" }],
  languages: [{ code: "en", name: "English" }],
  licenseState: "VA",
  licenseStateName: "Virginia",
  headshotPath: "/hub/agent-directory/42/headshot",
};

function setPage(overrides: Partial<AgentDirectoryPageProps> = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "viewer@onest.realestate",
      name: "Viewer",
      headshotUrl: null,
      permissions: [],
      roles: ["Realtor"],
      roleLabel: "Realtor",
      isStaff: false,
      isSuperuser: false,
    },
    csrfToken: "token",
    requestId: "req-1",
    features: { "agent-directory": true },
    primaryOffice: null,
    shell: {
      authorizationVersion: "v1",
      capabilitySchemaVersion: "p0-permissions-v1",
      help: { url: "https://help.example.com" },
      session: { authenticated: true },
    },
    notifications: null,
    people: {
      items: [person],
      pagination: {
        page: 1,
        pageSize: 24,
        totalItems: 1,
        totalPages: 1,
        hasNext: false,
        hasPrevious: false,
      },
      filters: {
        q: "",
        office: "",
        region: "",
        role: "",
        licenseState: "",
        specialty: "",
        language: "",
        view: "grid",
      },
      sort: { key: "name", direction: "asc" },
    },
    filterOptions: {
      offices: [{ value: "7", label: "Fairfax VA" }],
      regions: [{ value: "1", label: "Mid-Atlantic" }],
      roles: [{ value: "realtor", label: "Realtor" }],
      licenseStates: [{ value: "VA", label: "Virginia" }],
      specialties: [{ value: "residential", label: "Residential" }],
      languages: [{ value: "en", label: "English" }],
    },
    empty: null,
    ...overrides,
  } as AgentDirectoryPageProps;
}

describe("AgentDirectory", () => {
  beforeEach(() => {
    setPage();
    routerGet.mockReset();
  });

  it("renders allowlisted person fields and accessible contact actions", async () => {
    const { container } = render(<AgentDirectory />);
    expect(
      screen.getByRole("heading", { name: "Agent directory" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Ada Agent")).toBeInTheDocument();
    expect(screen.getByText("Residential")).toBeInTheDocument();

    const call = screen.getByRole("link", {
      name: "Call work phone for Ada Agent",
    });
    expect(call).toHaveAttribute("href", "tel:(703) 555-0100");
    const email = screen.getByRole("link", { name: "Email Ada Agent at work" });
    expect(email).toHaveAttribute("href", "mailto:ada@onest.realestate");

    expect(container.textContent).not.toContain("internalNotes");
    expect(container.textContent).not.toContain("agentIdentifier");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows image failure fallback when the headshot errors", () => {
    render(<AgentDirectory />);
    const img = document.querySelector(
      'img[src="/hub/agent-directory/42/headshot"]',
    ) as HTMLImageElement;
    expect(img).toBeTruthy();
    fireEvent.error(img);
    expect(
      document.querySelector('img[src="/hub/agent-directory/42/headshot"]'),
    ).toBeNull();
  });

  it("shows the empty state when the server reports no results", () => {
    setPage({
      people: {
        ...pageProps.current.people,
        items: [],
        pagination: {
          ...pageProps.current.people.pagination,
          totalItems: 0,
        },
      },
      empty: {
        kind: "no-results",
        title: "No matching people",
        description: "Try a different name or clear one of the filters.",
      },
    });
    render(<AgentDirectory />);
    expect(screen.getByText("No matching people")).toBeInTheDocument();
  });

  it("toggles list view through the URL helper", async () => {
    const user = userEvent.setup();
    render(<AgentDirectory />);
    await user.click(screen.getByRole("button", { name: "List view" }));
    expect(routerGet).toHaveBeenCalled();
    const url = String(routerGet.mock.calls[0]?.[0] ?? "");
    expect(url).toContain("view=list");
  });
});
