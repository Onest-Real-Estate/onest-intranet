import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

const { pageProps, routerGet } = vi.hoisted(() => {
  const item = {
    id: 1,
    slug: "brand-logo",
    title: "Primary brand logo",
    description: "Approved primary mark",
    assetType: {
      code: "logo",
      label: "Logo",
      tone: "brand",
      known: true,
    },
    category: {
      code: "logos",
      label: "Logos",
      tone: "neutral",
      known: true,
    },
    scope: { level: "company", label: "Brokerage-wide", officeName: "oNEST" },
    jurisdictionStateCodes: [] as string[],
    brandCodes: [] as string[],
    versionNumber: 1,
    versionLabel: "v1",
    previewUrl: "",
    exportCount: 2,
    publishedAt: "2026-01-01T00:00:00Z",
    detailUrl: "/marketing-resources/1",
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
          type: "",
          jurisdiction: "",
          brand: "",
          q: "",
          rejected: [] as string[],
        },
      },
      filterOptions: {
        categories: [{ value: "logos", label: "Logos" }],
        assetTypes: [{ value: "logo", label: "Logo" }],
      },
      summary: {
        published: 1,
        logos: 1,
        templates: 0,
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

import MarketingResources from "@/pages/MarketingResources";

const libraryItem = pageProps.library.items[0];

function resetLibrary() {
  pageProps.library.items = [libraryItem];
  pageProps.library.pagination.totalItems = 1;
  pageProps.library.pagination.totalPages = 1;
  pageProps.library.filters = {
    category: "",
    type: "",
    jurisdiction: "",
    brand: "",
    q: "",
    rejected: [],
  };
}

describe("MarketingResources", () => {
  beforeEach(() => {
    resetLibrary();
    routerGet.mockClear();
  });

  it("renders library rows and filter controls", () => {
    render(<MarketingResources />);
    expect(screen.getByRole("heading", { name: "Marketing" })).toBeInTheDocument();
    expect(screen.getByText("Primary brand logo")).toBeInTheDocument();
    expect(screen.getByText("Published")).toBeInTheDocument();
    expect(screen.getByLabelText("Search marketing resources")).toBeInTheDocument();
  });

  it("shows an empty state when nothing matches", () => {
    pageProps.library.items = [];
    pageProps.library.pagination.totalItems = 0;
    pageProps.library.filters.category = "logos";
    render(<MarketingResources />);
    expect(
      screen.getByText("No marketing resources match these filters"),
    ).toBeInTheDocument();
  });

  it("requests a filtered visit through Inertia", async () => {
    const user = userEvent.setup();
    render(<MarketingResources />);
    await user.click(screen.getByRole("button", { name: /filters/i }));
    await user.click(screen.getByLabelText("Category"));
    await user.click(screen.getByRole("option", { name: "Logos" }));
    expect(routerGet).toHaveBeenCalled();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<MarketingResources />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
