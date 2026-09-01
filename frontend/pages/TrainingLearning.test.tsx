import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const { pageProps, routerGet } = vi.hoisted(() => ({
  routerGet: vi.fn(),
  pageProps: {
    library: {
      items: [
        {
          id: 1,
          slug: "ethics",
          title: "Ethics overview",
          summary: "Annual ethics training",
          contentType: {
            code: "article",
            label: "Article",
            tone: "neutral",
            known: true,
          },
          category: {
            code: "ethics",
            label: "Ethics",
            tone: "neutral",
            known: true,
          },
          scope: { level: "company", label: "Brokerage-wide", officeName: "oNEST" },
          isRequired: true,
          estimatedMinutes: 15,
          toolCode: null,
          completion: { status: "not_started", label: "Not started" },
          publishedAt: "2026-01-01T00:00:00Z",
          detailUrl: "/training-learning/1",
        },
      ],
      pagination: {
        page: 1,
        pageSize: 12,
        totalItems: 1,
        totalPages: 1,
      },
      filters: {
        category: "",
        type: "",
        required: "",
        tool: "",
        completion: "",
        view: "all",
        q: "",
        rejected: [],
      },
    },
    filterOptions: {
      categories: [{ value: "ethics", label: "Ethics" }],
      contentTypes: [{ value: "article", label: "Article" }],
      tools: [],
      completions: [{ value: "not_started", label: "Not started" }],
    },
  },
}));

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

import TrainingLearning from "@/pages/TrainingLearning";

describe("TrainingLearning", () => {
  it("renders required training and accessible filters", () => {
    render(<TrainingLearning />);
    expect(
      screen.getByRole("heading", { name: "Training & learning" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Ethics overview")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Required", pressed: false }),
    ).toBeInTheDocument();
    const card = screen.getByRole("article", { name: "Ethics overview" });
    expect(within(card).getByText("Required")).toBeInTheDocument();
  });

  it("requests the required view through Inertia", async () => {
    const user = userEvent.setup();
    render(<TrainingLearning />);
    await user.click(screen.getByRole("button", { name: "Required" }));
    expect(routerGet).toHaveBeenCalled();
  });

  it("shows an empty state when nothing matches", () => {
    pageProps.library.items = [];
    pageProps.library.pagination.totalItems = 0;
    pageProps.library.filters.view = "required";
    render(<TrainingLearning />);
    expect(screen.getByText("No training matches these filters")).toBeInTheDocument();
    pageProps.library.items = [
      {
        id: 1,
        slug: "ethics",
        title: "Ethics overview",
        summary: "Annual ethics training",
        contentType: {
          code: "article",
          label: "Article",
          tone: "neutral",
          known: true,
        },
        category: {
          code: "ethics",
          label: "Ethics",
          tone: "neutral",
          known: true,
        },
        scope: { level: "company", label: "Brokerage-wide", officeName: "oNEST" },
        isRequired: true,
        estimatedMinutes: 15,
        toolCode: null,
        completion: { status: "not_started", label: "Not started" },
        publishedAt: "2026-01-01T00:00:00Z",
        detailUrl: "/training-learning/1",
      },
    ];
    pageProps.library.pagination.totalItems = 1;
    pageProps.library.filters.view = "all";
  });
});
