import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AnnouncementDetail from "@/pages/AnnouncementDetail";
import type {
  AnnouncementDetailPageProps,
  AnnouncementDetail as AnnouncementDetailType,
  AnnouncementMedia as AnnouncementMediaType,
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
    isPinned: false,
    cta: null,
    // Mirrors `body` above: the server derives the blocks from that source,
    // so a fixture where they disagree would be testing a payload that cannot
    // occur.
    bodyBlocks: [
      {
        type: "paragraph",
        spans: [{ type: "text", value: "The Fairfax office is closed Monday." }],
      },
    ],
    audience: [
      {
        kind: "office",
        label: "Fairfax, VA",
        code: "",
        officeId: 6,
        userId: null,
      },
    ],
    hero: null,
    attachments: [],
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

function mediaFile(overrides: Partial<AnnouncementMediaType> = {}) {
  return {
    id: 31,
    role: "attachment" as const,
    displayName: "memo.pdf",
    mediaType: "application/pdf",
    byteSize: 2048,
    width: null,
    height: null,
    isImage: false,
    url: "/announcements/media/31",
    variants: {},
    ...overrides,
  };
}

describe("attachments", () => {
  it("offers no files section when there are none", () => {
    render(<AnnouncementDetail />);
    expect(screen.queryByRole("link", { name: /memo/ })).not.toBeInTheDocument();
  });

  it("points each download at the re-authorized media route", () => {
    pageProps = {
      announcement: detail({ attachments: [mediaFile()] }),
    } as AnnouncementDetailPageProps;
    render(<AnnouncementDetail />);

    const link = screen.getByRole("link", { name: /memo\.pdf/ });
    expect(link).toHaveAttribute("href", "/announcements/media/31");
    // A plain anchor, not an Inertia visit: the browser must own the download.
    expect(link).toHaveAttribute("download");
  });

  it("shows each file's size so a reader knows what they are opening", () => {
    pageProps = {
      announcement: detail({ attachments: [mediaFile({ byteSize: 3_500_000 })] }),
    } as AnnouncementDetailPageProps;
    render(<AnnouncementDetail />);
    expect(screen.getByText("3.3 MB")).toBeInTheDocument();
  });
});

describe("hero image", () => {
  const hero = mediaFile({
    id: 9,
    role: "hero" as const,
    mediaType: "image/png",
    isImage: true,
    width: 1600,
    height: 900,
    url: "/announcements/media/9",
    variants: {
      thumb: "/announcements/media/9/thumb",
      card: "/announcements/media/9/card",
      hero: "/announcements/media/9/hero",
    },
  });

  it("renders responsive sources from the generated variants", () => {
    pageProps = {
      announcement: detail({ hero }),
    } as AnnouncementDetailPageProps;
    const { container } = render(<AnnouncementDetail />);

    const image = container.querySelector("img");
    expect(image).toHaveAttribute("src", "/announcements/media/9/hero");
    expect(image?.getAttribute("srcset")).toContain("320w");
    expect(image?.getAttribute("srcset")).toContain("1600w");
  });

  it("is decorative, because the headline already carries the meaning", () => {
    pageProps = {
      announcement: detail({ hero }),
    } as AnnouncementDetailPageProps;
    const { container } = render(<AnnouncementDetail />);
    expect(container.querySelector("img")).toHaveAttribute("alt", "");
  });

  it("falls back to the original when no variants were generated", () => {
    pageProps = {
      announcement: detail({ hero: { ...hero, variants: {} } }),
    } as AnnouncementDetailPageProps;
    const { container } = render(<AnnouncementDetail />);

    const image = container.querySelector("img");
    expect(image).toHaveAttribute("src", "/announcements/media/9");
    expect(image?.getAttribute("srcset")).toBeNull();
  });

  it("degrades to the text layout when there is no hero at all", () => {
    const { container } = render(<AnnouncementDetail />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });

  it("removes a hero that fails to load rather than leaving a broken image", () => {
    pageProps = {
      announcement: detail({ hero }),
    } as AnnouncementDetailPageProps;
    const { container } = render(<AnnouncementDetail />);

    const image = container.querySelector("img");
    expect(image).not.toBeNull();
    fireEvent.error(image as HTMLImageElement);

    expect(container.querySelector("img")).toBeNull();
    // The article is still complete without it.
    expect(
      screen.getByText("The Fairfax office is closed Monday."),
    ).toBeInTheDocument();
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
