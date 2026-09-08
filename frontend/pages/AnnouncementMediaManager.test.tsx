import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AnnouncementMediaManager from "@/pages/AnnouncementMediaManager";
import type {
  AnnouncementMediaAdmin,
  AnnouncementMediaManagerPageProps,
} from "@/types";

const routerPost = vi.fn();
const routerReload = vi.fn();

vi.mock("@inertiajs/react", () => ({
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: {
    post: (...args: unknown[]) => routerPost(...args),
    reload: (...args: unknown[]) => routerReload(...args),
  },
  usePage: () => ({ props: pageProps }),
}));

vi.mock("@/components/PermissionRequired", () => ({
  PermissionRequired: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

let pageProps: AnnouncementMediaManagerPageProps;

function file(overrides: Partial<AnnouncementMediaAdmin> = {}): AnnouncementMediaAdmin {
  const id = overrides.id ?? 1;
  return {
    id,
    role: "attachment",
    displayName: "memo.pdf",
    mediaType: "application/pdf",
    byteSize: 2048,
    width: null,
    height: null,
    isImage: false,
    url: `/announcements/media/${id}`,
    variants: {},
    processingState: "ready",
    processingNote: "",
    isActive: true,
    checksum: "a".repeat(64),
    sortOrder: 0,
    ...overrides,
  };
}

function props(
  overrides: Partial<AnnouncementMediaManagerPageProps> = {},
): AnnouncementMediaManagerPageProps {
  return {
    announcement: { id: 7, title: "Office closed Monday", status: "draft" },
    media: { hero: null, attachments: [] },
    limits: {
      hero: { extensions: [".png", ".jpg"], maxBytes: 8 * 1024 * 1024, minWidth: 600 },
      attachment: {
        extensions: [".pdf", ".txt"],
        maxBytes: 20 * 1024 * 1024,
        maxCount: 10,
      },
    },
    validation: { fields: {}, form: [] },
    ...overrides,
  } as AnnouncementMediaManagerPageProps;
}

beforeEach(() => {
  routerPost.mockClear();
  routerReload.mockClear();
  pageProps = props();
});

describe("layout", () => {
  it("separates the hero from the attachments", () => {
    render(<AnnouncementMediaManager />);
    expect(screen.getByRole("region", { name: "Hero image" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Attachments" })).toBeInTheDocument();
  });

  it("states the allowed types and size for each slot", () => {
    render(<AnnouncementMediaManager />);
    expect(screen.getByText(/\.png, \.jpg/)).toBeInTheDocument();
    expect(screen.getByText(/at least 600px wide/)).toBeInTheDocument();
    expect(screen.getByText(/10 files maximum/)).toBeInTheDocument();
  });

  it("shows an empty state before anything is attached", () => {
    render(<AnnouncementMediaManager />);
    expect(screen.getByText("No attachments yet")).toBeInTheDocument();
  });
});

describe("processing state", () => {
  it("labels a file that is still being checked", () => {
    pageProps = props({
      media: { hero: null, attachments: [file({ processingState: "pending" })] },
    });
    render(<AnnouncementMediaManager />);
    expect(screen.getByText("Processing")).toBeInTheDocument();
  });

  it("warns that publication is blocked while anything is unprocessed", () => {
    pageProps = props({
      media: { hero: null, attachments: [file({ processingState: "pending" })] },
    });
    render(<AnnouncementMediaManager />);
    expect(screen.getByRole("status")).toHaveTextContent(/cannot be published/);
  });

  it("surfaces the quarantine reason to the administrator", () => {
    pageProps = props({
      media: {
        hero: null,
        attachments: [
          file({
            processingState: "quarantined",
            processingNote: "Stored bytes do not match the upload checksum.",
          }),
        ],
      },
    });
    render(<AnnouncementMediaManager />);
    expect(screen.getByText("Quarantined")).toBeInTheDocument();
    expect(screen.getByText(/do not match the upload checksum/)).toBeInTheDocument();
  });

  it("says nothing about blocking when every file is ready", () => {
    pageProps = props({ media: { hero: null, attachments: [file()] } });
    render(<AnnouncementMediaManager />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

describe("reordering", () => {
  const three = [
    file({ id: 1, displayName: "a.pdf" }),
    file({ id: 2, displayName: "b.pdf" }),
    file({ id: 3, displayName: "c.pdf" }),
  ];

  beforeEach(() => {
    pageProps = props({ media: { hero: null, attachments: three } });
  });

  it("is reachable from the keyboard, not drag-only", () => {
    render(<AnnouncementMediaManager />);
    expect(screen.getByRole("button", { name: "Move b.pdf up" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move b.pdf down" })).toBeInTheDocument();
  });

  it("disables the moves that would fall off either end", () => {
    render(<AnnouncementMediaManager />);
    expect(screen.getByRole("button", { name: "Move a.pdf up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move c.pdf down" })).toBeDisabled();
  });

  it("persists the new order immediately", async () => {
    render(<AnnouncementMediaManager />);
    await userEvent.click(screen.getByRole("button", { name: "Move c.pdf up" }));

    expect(routerPost).toHaveBeenCalled();
    const [url, payload] = routerPost.mock.calls[0];
    expect(url).toBe("/operations/announcements/7/media/reorder");
    expect(payload).toEqual({ order: ["1", "3", "2"] });
  });

  it("moves with the keyboard alone", async () => {
    render(<AnnouncementMediaManager />);
    const button = screen.getByRole("button", { name: "Move b.pdf up" });
    button.focus();
    await userEvent.keyboard("{Enter}");
    expect(routerPost.mock.calls[0][1]).toEqual({ order: ["2", "1", "3"] });
  });
});

describe("removal", () => {
  it("posts to the remove route for that file", async () => {
    pageProps = props({ media: { hero: null, attachments: [file({ id: 42 })] } });
    render(<AnnouncementMediaManager />);

    await userEvent.click(screen.getByRole("button", { name: "Remove memo.pdf" }));
    expect(routerPost.mock.calls[0][0]).toBe(
      "/operations/announcements/media/42/remove",
    );
  });
});

describe("downloads", () => {
  it("links each file at its audience-checked media route", () => {
    pageProps = props({ media: { hero: null, attachments: [file({ id: 42 })] } });
    render(<AnnouncementMediaManager />);

    const list = screen.getByRole("list", { name: "Attachments" });
    const link = within(list).getByRole("link", { name: "Download memo.pdf" });
    expect(link).toHaveAttribute("href", "/announcements/media/42");
  });
});
