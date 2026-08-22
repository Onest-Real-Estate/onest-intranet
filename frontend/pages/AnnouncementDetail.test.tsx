import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AnnouncementDetail from "@/pages/AnnouncementDetail";
import type {
  AnnouncementDetailPageProps,
  AnnouncementDetail as AnnouncementDetailType,
} from "@/types";

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: vi.fn() },
  usePage: () => ({ props: pageProps }),
}));

let pageProps: AnnouncementDetailPageProps;

function detail(
  overrides: Partial<AnnouncementDetailType> = {},
): AnnouncementDetailType {
  return {
    id: 7,
    slug: "office-closed",
    title: "Office closed Monday",
    summary: "Holiday closure.",
    body: "The Fairfax office is closed Monday.",
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
      code: "urgent",
      label: "Urgent",
      tone: "destructive",
      srLabel: "Priority: Urgent",
      known: true,
      rank: 1,
    },
    scope: { level: "office", label: "Office", officeName: "Fairfax, VA" },
    audience: [
      {
        kind: "office",
        label: "Fairfax, VA",
        code: "",
        officeId: 6,
        userId: null,
      },
    ],
    hasAttachment: false,
    attachmentName: "",
    ...overrides,
  };
}

beforeEach(() => {
  pageProps = { announcement: detail() } as AnnouncementDetailPageProps;
});

describe("audience disclosure", () => {
  it("names each selector the announcement was addressed to", () => {
    pageProps = {
      announcement: detail({
        audience: [
          {
            kind: "region",
            label: "Mid-Atlantic and offices under it",
            code: "",
            officeId: 2,
            userId: null,
          },
          {
            kind: "role",
            label: "Transaction Coordinator",
            code: "transaction_coordinator",
            officeId: null,
            userId: null,
          },
        ],
      }),
    } as AnnouncementDetailPageProps;
    render(<AnnouncementDetail />);

    const section = screen.getByRole("region", { name: "Who this was sent to" });
    expect(
      within(section).getByText("Mid-Atlantic and offices under it"),
    ).toBeInTheDocument();
    expect(within(section).getByText("Transaction Coordinator")).toBeInTheDocument();
  });

  it("states union semantics rather than letting the list imply an AND", () => {
    pageProps = {
      announcement: detail({
        audience: [
          { kind: "office", label: "Fairfax, VA", code: "", officeId: 6, userId: null },
          {
            kind: "role",
            label: "Compliance",
            code: "compliance",
            officeId: null,
            userId: null,
          },
        ],
      }),
    } as AnnouncementDetailPageProps;
    render(<AnnouncementDetail />);
    expect(
      screen.getByText(/anyone matching any of these 2 audiences/),
    ).toBeInTheDocument();
  });

  it("reads naturally for a single audience", () => {
    render(<AnnouncementDetail />);
    expect(screen.getByText("Sent to Fairfax, VA.")).toBeInTheDocument();
  });
});

describe("classification", () => {
  it("shows priority and category in words as well as tone", () => {
    render(<AnnouncementDetail />);
    expect(screen.getByText("Urgent")).toBeInTheDocument();
    expect(screen.getByText("Office Notice")).toBeInTheDocument();
    expect(
      screen.getByText("Priority: Urgent. Category: Office Notice."),
    ).toBeInTheDocument();
  });
});

describe("attachment", () => {
  it("offers no download when there is no attachment", () => {
    render(<AnnouncementDetail />);
    expect(screen.queryByRole("link", { name: /Download/ })).not.toBeInTheDocument();
  });

  it("points the download at the re-authorized attachment route", () => {
    pageProps = {
      announcement: detail({ hasAttachment: true, attachmentName: "memo.pdf" }),
    } as AnnouncementDetailPageProps;
    render(<AnnouncementDetail />);

    const link = screen.getByRole("link", { name: /Download \(memo\.pdf\)/ });
    expect(link).toHaveAttribute("href", "/announcements/7/attachment");
    // A plain anchor, not an Inertia visit: the browser must own the download.
    expect(link).toHaveAttribute("download");
  });
});

describe("navigation", () => {
  it("offers a way back to the feed", () => {
    render(<AnnouncementDetail />);
    expect(screen.getByRole("link", { name: /All announcements/ })).toHaveAttribute(
      "href",
      "/announcements",
    );
  });
});
