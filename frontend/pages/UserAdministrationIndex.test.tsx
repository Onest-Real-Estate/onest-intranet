import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import UserAdministrationIndex from "@/pages/UserAdministrationIndex";
import type { UserAdministrationIndexPageProps } from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as UserAdministrationIndexPageProps,
}));
const routerGet = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({
    props: pageProps.current,
    url: "/operations/users/administration",
  }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: routerGet },
}));

function setPage(overrides: Partial<UserAdministrationIndexPageProps> = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "ada@onest.realestate",
      name: "Ada Admin",
      headshotUrl: null,
      permissions: ["user.view_user_administration"],
      roles: ["Branch Manager"],
      roleLabel: "Branch Manager",
      isStaff: false,
      isSuperuser: false,
    },
    csrfToken: "token",
    requestId: "req-1",
    features: {},
    primaryOffice: null,
    shell: {
      authorizationVersion: "v1",
      capabilitySchemaVersion: "p0-permissions-v1",
      help: { url: null },
      session: { authenticated: true },
    },
    users: {
      items: [
        {
          id: 9,
          name: "Bob Lee",
          email: "bob@onest.realestate",
          officeName: "Fairfax VA",
          agentStatus: "active",
          agentIdentifier: "ON-4412",
          isActive: true,
        },
      ],
      pagination: {
        page: 1,
        pageSize: 25,
        totalItems: 1,
        totalPages: 1,
        hasNext: false,
        hasPrevious: false,
      },
      filters: { q: "" },
      sort: { key: "name", direction: "asc" },
    },
    statusOptions: [{ value: "active", label: "Active", tone: "success" }],
    ...overrides,
  } as UserAdministrationIndexPageProps;
}

beforeEach(() => {
  routerGet.mockClear();
  setPage();
});

describe("UserAdministrationIndex", () => {
  it("lists the people the server put in scope, with a way into each record", () => {
    render(<UserAdministrationIndex />);
    const row = screen
      .getAllByRole("row")
      .find((candidate) => candidate.textContent?.includes("Bob Lee"));
    expect(row).toBeDefined();
    expect(
      within(row as HTMLElement).getByRole("link", { name: /administer/i }),
    ).toHaveAttribute("href", "/operations/users/9/administration");
  });

  it("sends the search to the server rather than filtering in the browser", async () => {
    const user = userEvent.setup();
    render(<UserAdministrationIndex />);
    await user.type(screen.getByLabelText(/search people/i), "bob{Enter}");
    expect(routerGet).toHaveBeenCalledWith(
      "/operations/users/administration",
      expect.objectContaining({ q: "bob" }),
      expect.anything(),
    );
  });

  it("explains an empty scope rather than showing a bare empty table", () => {
    setPage({
      users: {
        items: [],
        pagination: {
          page: 1,
          pageSize: 25,
          totalItems: 0,
          totalPages: 1,
          hasNext: false,
          hasPrevious: false,
        },
        filters: { q: "" },
        sort: null,
      },
    });
    render(<UserAdministrationIndex />);
    expect(screen.getByText(/does not scope you to anybody yet/i)).toBeVisible();
  });

  it("has no detectable accessibility violations", async () => {
    const { container } = render(<UserAdministrationIndex />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
