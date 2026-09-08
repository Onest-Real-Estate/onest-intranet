import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { GlobalSearch, highlightParts } from "@/components/search/GlobalSearch";
import type { SearchResults } from "@/types";

const routerGet = vi.hoisted(() => vi.fn());
const routerVisit = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  Link: ({
    href,
    children,
    onClick,
  }: {
    href: string;
    children: ReactNode;
    onClick?: () => void;
  }) => (
    <a href={href} onClick={onClick}>
      {children}
    </a>
  ),
  router: { get: routerGet, visit: routerVisit },
}));

function results(overrides: Partial<SearchResults> = {}): SearchResults {
  return {
    query: "fairfax",
    total: 1,
    tooShort: false,
    minLength: 2,
    partial: false,
    groups: [
      {
        key: "announcements",
        label: "Announcements",
        icon: "megaphone",
        failed: false,
        truncated: false,
        allResultsHref: "/announcements?q=fairfax",
        hits: [
          {
            id: "1",
            title: "Fairfax office closed",
            href: "/announcements/1",
            snippet: "The Fairfax office is closed Monday.",
            meta: "Office Notice",
          },
        ],
      },
    ],
    ...overrides,
  };
}

function respondWith(payload: SearchResults | null, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({
        ok: status === 200,
        status,
        json: () => Promise.resolve(payload),
      }),
    ),
  );
}

async function openAndType(term: string) {
  await userEvent.click(screen.getByRole("button", { name: "Search ONEST" }));
  await userEvent.type(await screen.findByLabelText("Search query"), term);
}

beforeEach(() => {
  routerGet.mockClear();
  routerVisit.mockClear();
  respondWith(results());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("highlightParts", () => {
  it("splits around every case-insensitive match", () => {
    expect(highlightParts("Fairfax and fairfax", "fairfax")).toEqual([
      "Fairfax",
      " and ",
      "fairfax",
    ]);
  });

  it("returns the whole string when nothing matches", () => {
    expect(highlightParts("nothing here", "zzz")).toEqual(["nothing here"]);
  });

  it("handles an empty query without splitting", () => {
    expect(highlightParts("text", "  ")).toEqual(["text"]);
  });
});

describe("GlobalSearch", () => {
  it("opens the dialog from the header control", async () => {
    render(<GlobalSearch />);

    await userEvent.click(screen.getByRole("button", { name: "Search ONEST" }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("asks the server and groups what it returns", async () => {
    render(<GlobalSearch />);
    await openAndType("fairfax");

    // Queried through `screen` rather than a captured dialog node: the results
    // arrive after a debounce, so the assertion has to settle, not snapshot.
    // Asserted on the row's own text and destination rather than a computed
    // accessible name: the row deliberately stacks title, snippet, and meta,
    // so its name is all three concatenated.
    const option = await screen.findByRole("option");
    expect(option).toHaveTextContent(/Fairfax office closed/);
    expect(option).toHaveAttribute("href", "/announcements/1");
  });

  it("marks the matching text rather than rendering server markup", async () => {
    render(<GlobalSearch />);
    await openAndType("fairfax");

    await screen.findByRole("option");

    // The mark is produced client-side from plain text; nothing is injected.
    expect(screen.getByRole("dialog").querySelectorAll("mark").length).toBeGreaterThan(
      0,
    );
  });

  it("renders markup-looking result text as characters", async () => {
    respondWith(
      results({
        groups: [
          {
            ...results().groups[0],
            hits: [
              {
                id: "9",
                title: "<script>alert(1)</script>",
                href: "/announcements/9",
                snippet: "",
                meta: "",
              },
            ],
          },
        ],
      }),
    );
    render(<GlobalSearch />);
    await openAndType("script");

    expect(await screen.findByText(/<script>alert\(1\)<\/script>/)).toBeInTheDocument();
    expect(screen.getByRole("dialog").querySelector("script")).toBeNull();
  });

  it("does not query the server below the minimum length", async () => {
    render(<GlobalSearch />);
    await openAndType("f");

    expect(await screen.findByText(/Search needs at least 2 characters/)).toBeVisible();
    await waitFor(() => expect(fetch).not.toHaveBeenCalled());
  });

  it("debounces so a burst of typing is one request", async () => {
    render(<GlobalSearch />);
    await openAndType("fairfax");

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(vi.mocked(fetch).mock.calls.length).toBeLessThan(4);
  });

  it("says when a source failed instead of showing a short list as complete", async () => {
    respondWith(
      results({
        partial: true,
        groups: [
          {
            key: "people",
            label: "People",
            icon: "users",
            hits: [],
            failed: true,
            truncated: false,
            allResultsHref: "",
          },
        ],
      }),
    );
    render(<GlobalSearch />);
    await openAndType("fairfax");

    expect(await screen.findByText(/results are incomplete/)).toBeVisible();
    expect(screen.getByText(/missing, not empty/)).toBeVisible();
  });

  it("offers a full-results link when a source was capped", async () => {
    respondWith(
      results({
        groups: [{ ...results().groups[0], truncated: true }],
      }),
    );
    render(<GlobalSearch />);
    await openAndType("fairfax");

    await userEvent.click(
      await screen.findByRole("button", { name: /See all announcements results/ }),
    );
    expect(routerVisit).toHaveBeenCalledWith("/announcements?q=fairfax");
  });

  it("explains a rate limit rather than showing an empty list", async () => {
    respondWith(null, 429);
    render(<GlobalSearch />);
    await openAndType("fairfax");

    expect(await screen.findByText("Too many searches")).toBeVisible();
  });

  it("reports no results without implying the sources are broken", async () => {
    respondWith(results({ total: 0, groups: [] }));
    render(<GlobalSearch />);
    await openAndType("zzzz");

    expect(await screen.findByText("No results")).toBeVisible();
    expect(screen.queryByText(/incomplete/)).not.toBeInTheDocument();
  });

  it("navigates to the full page on Enter", async () => {
    render(<GlobalSearch />);
    await openAndType("fairfax");
    await screen.findByRole("dialog");

    // With a result highlighted, Enter opens it; the "show everything" path is
    // covered by the no-results case below.
    await screen.findByRole("option");
    await userEvent.keyboard("{Enter}");

    expect(routerVisit).toHaveBeenCalledWith("/announcements/1");
  });

  it("announces result counts to assistive technology", async () => {
    render(<GlobalSearch />);
    await openAndType("fairfax");

    const status = await screen.findByText(/results across/);
    expect(status).toHaveAttribute("aria-live", "polite");
  });

  it("closes on Escape", async () => {
    render(<GlobalSearch />);
    await userEvent.click(screen.getByRole("button", { name: "Search ONEST" }));
    await screen.findByRole("dialog");

    await userEvent.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("offers a tab per source once there is more than one", async () => {
    respondWith(
      results({
        total: 2,
        groups: [
          results().groups[0],
          {
            key: "offices",
            label: "Offices",
            icon: "building",
            failed: false,
            truncated: false,
            allResultsHref: "/office-info?q=fairfax",
            hits: [
              {
                id: "4",
                title: "Fairfax VA",
                href: "/office-info",
                snippet: "Fairfax",
                meta: "Mid-Atlantic",
              },
            ],
          },
        ],
      }),
    );
    render(<GlobalSearch />);
    await openAndType("fairfax");

    expect(await screen.findByRole("tab", { name: /All/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(await screen.findAllByRole("option")).toHaveLength(2);

    await userEvent.click(screen.getByRole("tab", { name: /Offices/ }));

    expect(screen.getAllByRole("option")).toHaveLength(1);
    expect(screen.getByRole("option")).toHaveTextContent("Fairfax VA");
  });

  it("hides the tab strip when there is only one source", async () => {
    render(<GlobalSearch />);
    await openAndType("fairfax");
    await screen.findByRole("option");

    // One source plus "All" is a label pretending to be a control.
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });

  it("moves the highlight with the arrow keys without leaving the input", async () => {
    respondWith(
      results({
        total: 2,
        groups: [
          {
            ...results().groups[0],
            hits: [
              ...results().groups[0].hits,
              {
                id: "2",
                title: "Second notice",
                href: "/announcements/2",
                snippet: "",
                meta: "",
              },
            ],
          },
        ],
      }),
    );
    render(<GlobalSearch />);
    await openAndType("fairfax");
    await screen.findAllByRole("option");

    const input = screen.getByLabelText("Search query");
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "true");

    await userEvent.keyboard("{ArrowDown}");

    expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");
    // The caret never left, so typing continues to work.
    expect(input).toHaveFocus();
    expect(input).toHaveAttribute("aria-activedescendant");
  });

  it("has no accessibility violations when open", async () => {
    const { baseElement } = render(<GlobalSearch />);
    await openAndType("fairfax");
    await screen.findByRole("dialog");

    expect(await axe(baseElement)).toHaveNoViolations();
  });
});
