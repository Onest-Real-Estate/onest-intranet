import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Announcements from "@/pages/Announcements";
import type { AnnouncementRow, AnnouncementsPageProps } from "@/types";
import type { ListResponse } from "@/types/design-system";

const routerGet = vi.fn();

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: (...args: unknown[]) => routerGet(...args) },
  usePage: () => ({ props: pageProps }),
}));

let pageProps: AnnouncementsPageProps;

function row(overrides: Partial<AnnouncementRow> = {}): AnnouncementRow {
  return {
    id: 1,
    slug: "office-closed",
    title: "Office closed Monday",
    summary: "The Fairfax office is closed for the holiday.",
    body: "",
    publishedAt: "2026-08-01T12:00:00Z",
    expiresAt: null,
    category: {
      code: "office_notice",
      label: "Office Notice",
      tone: "neutral",
      srLabel: "Category: Office Notice",
      known: true,
    },
    priority: {
      code: "normal",
      label: "Normal",
      tone: "neutral",
      srLabel: "Priority: Normal",
      known: true,
      rank: 3,
    },
    scope: { level: "office", label: "Office", officeName: "Fairfax, VA" },
    isPinned: false,
    cta: null,
    ...overrides,
  };
}

function feed(
  items: AnnouncementRow[],
  overrides: Partial<ListResponse<AnnouncementRow, never>> = {},
) {
  return {
    items,
    pagination: {
      page: 1,
      pageSize: 12,
      totalItems: items.length,
      totalPages: 1,
      hasNext: false,
      hasPrevious: false,
    },
    filters: { category: "", priority: "", rejected: [] },
    sort: { key: "priority", direction: "asc" as const },
    ...overrides,
  } as AnnouncementsPageProps["feed"];
}

function props(
  overrides: Partial<AnnouncementsPageProps> = {},
): AnnouncementsPageProps {
  return {
    feed: feed([row()]),
    filterOptions: {
      categories: [
        { value: "office_notice", label: "Office Notice" },
        { value: "compliance_update", label: "Compliance Update" },
      ],
      priorities: [
        { value: "urgent", label: "Urgent" },
        { value: "important", label: "Important" },
        { value: "normal", label: "Normal" },
      ],
    },
    ...overrides,
  } as AnnouncementsPageProps;
}

beforeEach(() => {
  routerGet.mockClear();
  window.history.replaceState({}, "", "/announcements");
  pageProps = props();
});

describe("badge semantics", () => {
  it("labels priority and category in words, not color alone", () => {
    pageProps = props({
      feed: feed([
        row({
          priority: {
            code: "urgent",
            label: "Urgent",
            tone: "destructive",
            srLabel: "Priority: Urgent",
            known: true,
            rank: 1,
          },
        }),
      ]),
    });
    render(<Announcements />);

    const article = screen.getByRole("article");
    expect(within(article).getByText("Urgent")).toBeInTheDocument();
    expect(within(article).getByText("Office Notice")).toBeInTheDocument();
  });

  it("repeats the classification as a sentence for assistive technology", () => {
    render(<Announcements />);
    expect(
      screen.getByText("Priority: Normal. Category: Office Notice."),
    ).toBeInTheDocument();
  });

  it("says so when a stored code was not recognized", () => {
    pageProps = props({
      feed: feed([
        row({
          priority: {
            code: "normal",
            label: "Normal",
            tone: "neutral",
            srLabel: "Priority: Normal (unrecognized code “blocker”, shown as normal)",
            known: false,
            rank: 3,
          },
        }),
      ]),
    });
    render(<Announcements />);
    expect(screen.getByText(/unrecognized code/)).toBeInTheDocument();
  });

  it("gives each announcement an accessible name from its headline", () => {
    render(<Announcements />);
    expect(
      screen.getByRole("article", { name: "Office closed Monday" }),
    ).toBeInTheDocument();
  });
});

describe("filter controls", () => {
  it("exposes both filters as labelled controls", () => {
    render(<Announcements />);
    expect(screen.getByRole("combobox", { name: "Category" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Priority" })).toBeInTheDocument();
  });

  it("puts the chosen category into the URL as its stable code", async () => {
    render(<Announcements />);
    await userEvent.click(screen.getByRole("combobox", { name: "Category" }));
    await userEvent.click(screen.getByRole("option", { name: "Compliance Update" }));

    expect(routerGet).toHaveBeenCalled();
    const url = routerGet.mock.calls[0][0] as string;
    expect(url).toContain("category=compliance_update");
    expect(url).toContain("page=1");
  });

  it("counts applied filters and clears them on reset", async () => {
    pageProps = props({
      feed: feed([row()], {
        filters: { category: "office_notice", priority: "urgent", rejected: [] },
      } as never),
    });
    render(<Announcements />);

    const filterSection = screen.getByRole("region", { name: "Filters" });
    expect(within(filterSection).getByText("2")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Reset/ }));
    const url = routerGet.mock.calls[0][0] as string;
    expect(url).not.toContain("category=");
    expect(url).not.toContain("priority=");
  });

  it("reports a filter the server refused to apply", () => {
    pageProps = props({
      feed: feed([row()], {
        filters: { category: "", priority: "", rejected: ["category"] },
      } as never),
    });
    render(<Announcements />);
    expect(screen.getByRole("status")).toHaveTextContent(/category filter/);
  });
});

describe("query persistence", () => {
  it("keeps the active filters when turning the page", async () => {
    window.history.replaceState(
      {},
      "",
      "/announcements?category=office_notice&priority=urgent",
    );
    pageProps = props({
      feed: feed([row()], {
        filters: { category: "office_notice", priority: "urgent", rejected: [] },
        pagination: {
          page: 1,
          pageSize: 2,
          totalItems: 6,
          totalPages: 3,
          hasNext: true,
          hasPrevious: false,
        },
      } as never),
    });
    render(<Announcements />);

    await userEvent.click(screen.getByRole("button", { name: /Next/ }));
    const url = routerGet.mock.calls[0][0] as string;
    expect(url).toContain("category=office_notice");
    expect(url).toContain("priority=urgent");
    expect(url).toContain("page=2");
  });

  it("never sends the rejected report back as a query value", async () => {
    pageProps = props({
      feed: feed([row()], {
        filters: { category: "", priority: "", rejected: ["category"] },
      } as never),
    });
    render(<Announcements />);
    await userEvent.click(screen.getByRole("combobox", { name: "Priority" }));
    await userEvent.click(screen.getByRole("option", { name: "Urgent" }));

    const url = routerGet.mock.calls[0][0] as string;
    expect(url).not.toContain("rejected");
  });

  it("hides pagination when there is only one page", () => {
    render(<Announcements />);
    expect(
      screen.queryByRole("navigation", { name: "Pagination" }),
    ).not.toBeInTheDocument();
  });
});

describe("empty states", () => {
  it("distinguishes an empty feed from an over-filtered one", () => {
    pageProps = props({ feed: feed([]) });
    const { unmount } = render(<Announcements />);
    expect(screen.getByText("No announcements yet")).toBeInTheDocument();
    unmount();

    pageProps = props({
      feed: feed([], {
        filters: { category: "office_notice", priority: "", rejected: [] },
      } as never),
    });
    render(<Announcements />);
    expect(
      screen.getByText("No announcements match these filters"),
    ).toBeInTheDocument();
  });
});

describe("ordering", () => {
  it("renders the server's order without re-sorting it", () => {
    pageProps = props({
      feed: feed([
        row({ id: 1, title: "Urgent outage" }),
        row({ id: 2, title: "Routine update" }),
      ]),
    });
    render(<Announcements />);
    const headings = screen.getAllByRole("heading", { level: 2 });
    expect(headings.map((node) => node.textContent)).toEqual([
      "Urgent outage",
      "Routine update",
    ]);
  });
});
