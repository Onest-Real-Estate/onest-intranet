import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

const { pageProps, routerGet } = vi.hoisted(() => {
  const item = {
    id: 1,
    key: "exclusive-buyer",
    name: "Exclusive buyer agreement",
    description: "Current approved buyer form",
    status: {
      code: "published",
      label: "Published",
      tone: "success",
      known: true,
    },
    category: {
      code: "buyer",
      label: "Buyer",
      tone: "neutral",
      known: true,
    },
    scope: {
      level: "company",
      label: "Brokerage-wide",
      officeName: "oNEST",
      officeId: "1",
    },
    jurisdictionStateCodes: [] as string[],
    versionNumber: 2,
    versionLabel: "v2",
    effectiveAt: "2026-01-01T00:00:00Z",
    expiresAt: null as string | null,
    publishedAt: "2026-01-01T00:00:00Z",
    fileCount: 1,
    detailUrl: "/documents-forms/1",
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
          office: "",
          role: "",
          q: "",
          rejected: [] as string[],
        },
      },
      filterOptions: {
        categories: [{ value: "buyer", label: "Buyer" }],
        offices: [{ value: "1", label: "Fairfax VA" }],
        roles: [{ value: "realtor", label: "Realtor" }],
      },
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

import DocumentsForms from "@/pages/DocumentsForms";

const libraryItem = pageProps.library.items[0];

function resetLibrary() {
  pageProps.library.items = [libraryItem];
  pageProps.library.pagination.totalItems = 1;
  pageProps.library.pagination.totalPages = 1;
  pageProps.library.filters = {
    category: "",
    jurisdiction: "",
    office: "",
    role: "",
    q: "",
    rejected: [],
  };
}

describe("DocumentsForms", () => {
  beforeEach(() => {
    resetLibrary();
    routerGet.mockClear();
  });

  it("renders library rows and filter controls", () => {
    render(<DocumentsForms />);
    expect(
      screen.getByRole("heading", { name: "Documents & forms" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Exclusive buyer agreement")).toBeInTheDocument();
    expect(screen.getByLabelText("Category")).toBeInTheDocument();
    expect(screen.getByLabelText("Office")).toBeInTheDocument();
    expect(screen.getByLabelText("Role")).toBeInTheDocument();
    expect(screen.getByLabelText("State")).toBeInTheDocument();
    expect(screen.getByLabelText("Search documents and forms")).toBeInTheDocument();
    expect(screen.getByText("v2 · Brokerage-wide · oNEST")).toBeInTheDocument();
  });

  it("shows an empty state when nothing matches", () => {
    pageProps.library.items = [];
    pageProps.library.pagination.totalItems = 0;
    pageProps.library.filters.category = "buyer";
    render(<DocumentsForms />);
    expect(screen.getByText("No documents match these filters")).toBeInTheDocument();
  });

  it("shows a notice when filters were rejected", () => {
    pageProps.library.filters.rejected = ["office"];
    render(<DocumentsForms />);
    expect(
      screen.getByText(
        "Some filters were ignored because they are not valid for this library.",
      ),
    ).toBeInTheDocument();
  });

  it("requests a filtered visit through Inertia", async () => {
    const user = userEvent.setup();
    render(<DocumentsForms />);
    await user.click(screen.getByLabelText("Category"));
    await user.click(screen.getByRole("option", { name: "Buyer" }));
    expect(routerGet).toHaveBeenCalled();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<DocumentsForms />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
