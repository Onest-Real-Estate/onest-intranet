import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

const { pageProps, routerGet } = vi.hoisted(() => {
  const item = {
    id: 1,
    title: "Code of conduct",
    summary: "How we work with clients and each other",
    status: {
      code: "published",
      label: "Published",
      tone: "success",
      known: true,
    },
    category: {
      code: "conduct",
      label: "Conduct",
      tone: "neutral",
      known: true,
    },
    scope: { level: "company", label: "Brokerage-wide", officeName: "oNEST" },
    jurisdictionStateCodes: [] as string[],
    versionNumber: 1,
    versionLabel: "v1",
    isMandatory: true,
    publishedAt: "2026-01-01T00:00:00Z",
    detailUrl: "/policies-compliance/1",
    acknowledged: false,
    required: true,
    dueAt: "2026-01-15T00:00:00Z",
    canAcknowledge: true,
    mustOpenDocument: false,
    documentAccessed: false,
  };

  return {
    routerGet: vi.fn(),
    pageProps: {
      library: {
        items: [item],
        pagination: {
          page: 1,
          pageSize: 12,
          totalItems: 1,
          totalPages: 1,
        },
        filters: {
          category: "",
          jurisdiction: "",
          q: "",
          rejected: [] as string[],
        },
      },
      filterOptions: {
        categories: [{ value: "conduct", label: "Conduct" }],
      },
      summary: {
        published: 1,
        outstanding: 1,
        overdue: 0,
      },
      errors: { fields: {}, form: [] as string[] },
    },
  };
});

vi.mock("@inertiajs/react", async () => {
  const actual =
    await vi.importActual<typeof import("@inertiajs/react")>("@inertiajs/react");
  return {
    ...actual,
    Head: ({ title }: { title: string }) => <title>{title}</title>,
    Link: ({ href, children }: { href: string; children: React.ReactNode }) => (
      <a href={href}>{children}</a>
    ),
    router: { get: routerGet },
    usePage: () => ({ props: pageProps }),
  };
});

import PoliciesCompliance from "@/pages/PoliciesCompliance";

const libraryItem = pageProps.library.items[0];

function resetLibrary() {
  pageProps.library.items = [libraryItem];
  pageProps.library.pagination.totalItems = 1;
  pageProps.library.pagination.totalPages = 1;
  pageProps.library.filters = {
    category: "",
    jurisdiction: "",
    q: "",
    rejected: [],
  };
}

describe("PoliciesCompliance", () => {
  beforeEach(() => {
    resetLibrary();
    routerGet.mockClear();
  });

  it("renders library rows and filter controls", () => {
    render(<PoliciesCompliance />);
    expect(screen.getByRole("heading", { name: "Policies" })).toBeInTheDocument();
    expect(screen.getByText("Code of conduct")).toBeInTheDocument();
    expect(screen.getByText("Outstanding")).toBeInTheDocument();
    expect(screen.getByLabelText("Search policies")).toBeInTheDocument();
  });

  it("shows an empty state when nothing matches", () => {
    pageProps.library.items = [];
    pageProps.library.pagination.totalItems = 0;
    pageProps.library.filters.category = "conduct";
    render(<PoliciesCompliance />);
    expect(screen.getByText("No policies match these filters")).toBeInTheDocument();
  });

  it("requests a filtered visit through Inertia", async () => {
    const user = userEvent.setup();
    render(<PoliciesCompliance />);
    await user.click(screen.getByRole("button", { name: /filters/i }));
    await user.click(screen.getByLabelText("Category"));
    await user.click(screen.getByRole("option", { name: "Conduct" }));
    expect(routerGet).toHaveBeenCalled();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<PoliciesCompliance />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
