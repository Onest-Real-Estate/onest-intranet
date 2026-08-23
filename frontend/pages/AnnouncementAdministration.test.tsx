import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import AnnouncementAdministration from "@/pages/AnnouncementAdministration";
import type {
  AnnouncementAdministrationPageProps,
  AnnouncementAdminRow,
} from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as AnnouncementAdministrationPageProps,
}));
const routerGet = vi.hoisted(() => vi.fn());
const routerPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/operations/announcements" }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: routerGet, post: routerPost },
}));

function row(overrides: Partial<AnnouncementAdminRow> = {}): AnnouncementAdminRow {
  return {
    id: 1,
    slug: "office-closed",
    title: "Office closed Monday",
    summary: "The Fairfax office is closed for the holiday.",
    lifecycle: { code: "live", label: "Live", tone: "success" },
    status: "published",
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
      rank: 30,
    },
    isPinned: false,
    ownerOffice: { id: 4, name: "Fairfax VA" },
    scopeLevel: "office",
    audience: [
      {
        kind: "office",
        label: "Fairfax VA",
        code: "",
        officeId: 4,
        userId: null,
      },
    ],
    publishAt: null,
    expiresAt: null,
    publishedAt: "2026-08-01T12:00:00Z",
    updatedAt: "2026-08-02T09:00:00Z",
    updatedBy: "Ada Admin",
    createdBy: "Ada Admin",
    version: "2026-08-02T09:00:00+00:00",
    ...overrides,
  };
}

function setPage(overrides: Partial<AnnouncementAdministrationPageProps> = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "ada@onest.realestate",
      name: "Ada Admin",
      headshotUrl: null,
      permissions: ["web.manage_announcements", "web.publish_announcements"],
      roles: ["branch_manager"],
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
    notifications: null,
    announcements: {
      items: [
        row(),
        row({
          id: 2,
          slug: "policy-change",
          title: "Policy change",
          lifecycle: { code: "draft", label: "Draft", tone: "neutral" },
          status: "draft",
          publishedAt: null,
        }),
      ],
      pagination: {
        page: 1,
        pageSize: 20,
        totalItems: 2,
        totalPages: 1,
        hasNext: false,
        hasPrevious: false,
      },
      filters: {
        q: "",
        lifecycle: "",
        category: "",
        priority: "",
        audience: "",
        author: "",
        office: "",
        publishedFrom: "",
        publishedTo: "",
      },
      sort: { key: "updatedAt", direction: "desc" },
    },
    filterOptions: {
      categories: [{ value: "office_notice", label: "Office Notice" }],
      priorities: [{ value: "normal", label: "Normal" }],
      offices: [{ value: 4, label: "Fairfax VA" }],
    },
    createOptions: {
      offices: [{ value: 4, label: "Fairfax VA" }],
      categories: [{ value: "office_notice", label: "Office Notice" }],
      priorities: [{ value: "normal", label: "Normal" }],
      audience: {
        canTargetCompany: false,
        regions: [{ value: 2, label: "Mid-Atlantic" }],
        offices: [{ value: 4, label: "Fairfax VA" }],
        roles: [{ value: "realtor", label: "Realtor" }],
      },
    },
    createSheet: null,
    capabilities: { canAuthor: true, canPublish: true, canPin: true },
    errors: { fields: {}, form: [] },
    ...overrides,
  } as AnnouncementAdministrationPageProps;
}

/** Read a FormData body back as plain entries, so assertions stay legible. */
function bodyOf(call: unknown[]): Record<string, string[]> {
  const body = call[1];
  if (!(body instanceof FormData)) {
    throw new Error(
      `Expected a FormData body, got ${typeof body}. Inertia sends a plain object as JSON, which never reaches Django's request.POST.`,
    );
  }
  const entries: Record<string, string[]> = {};
  for (const [key, value] of body.entries()) {
    entries[key] = [...(entries[key] ?? []), String(value)];
  }
  return entries;
}

beforeEach(() => {
  routerGet.mockClear();
  routerPost.mockClear();
  setPage();
});

describe("AnnouncementAdministration", () => {
  it("lists the announcements the server put in scope with their derived state", () => {
    render(<AnnouncementAdministration />);

    expect(screen.getByText("Office closed Monday")).toBeInTheDocument();
    expect(screen.getByText("Policy change")).toBeInTheDocument();
    expect(screen.getByText("Live")).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
  });

  it("shows who last edited each record and when", () => {
    render(<AnnouncementAdministration />);

    expect(screen.getAllByText("Ada Admin").length).toBeGreaterThan(0);
  });

  it("narrows the list through the URL rather than in the browser", async () => {
    render(<AnnouncementAdministration />);

    await userEvent.click(screen.getByLabelText("Filter by lifecycle"));
    await userEvent.click(await screen.findByRole("option", { name: "Draft" }));

    expect(routerGet).toHaveBeenCalledWith(
      "/operations/announcements",
      expect.objectContaining({ lifecycle: "draft", page: 1 }),
      expect.objectContaining({ replace: true }),
    );
  });

  it("sends the version token with a pin so a stale row cannot be reordered", async () => {
    render(<AnnouncementAdministration />);

    await userEvent.click(
      screen.getByRole("button", { name: /^Pin Office closed Monday$/ }),
    );

    expect(routerPost).toHaveBeenCalledWith(
      "/operations/announcements/1/pin",
      expect.any(FormData),
      expect.anything(),
    );
    expect(bodyOf(routerPost.mock.calls[0])).toEqual({
      pinned: ["on"],
      expected_version: ["2026-08-02T09:00:00+00:00"],
    });
  });

  it("offers no pin control without the pin grant", () => {
    setPage({ capabilities: { canAuthor: true, canPublish: true, canPin: false } });
    render(<AnnouncementAdministration />);

    expect(screen.queryByRole("button", { name: /^Pin / })).not.toBeInTheDocument();
  });

  it("explains the missing publication grant instead of hiding the queue", () => {
    setPage({ capabilities: { canAuthor: true, canPublish: false, canPin: false } });
    render(<AnnouncementAdministration />);

    expect(screen.getByText("Office closed Monday")).toBeInTheDocument();
    expect(screen.getByText(/need the publication grant/i)).toBeInTheDocument();
  });

  it("opens the create drawer in place instead of leaving the queue", async () => {
    render(<AnnouncementAdministration />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /New announcement/ }));

    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByLabelText(/^Title/)).toBeInTheDocument();
    expect(within(drawer).getByLabelText(/^Owning office/)).toBeInTheDocument();
    // The queue is still behind it — the drawer is not a navigation.
    expect(screen.getByText("Office closed Monday")).toBeInTheDocument();
    expect(routerGet).not.toHaveBeenCalled();
  });

  it("posts the drawer natively to the create route with the sheet marker", async () => {
    render(<AnnouncementAdministration />);
    await userEvent.click(screen.getByRole("button", { name: /New announcement/ }));

    const drawer = await screen.findByRole("dialog");
    const form = drawer.querySelector("form");
    expect(form).toHaveAttribute("action", "/operations/announcements/create");
    expect(form).toHaveAttribute("method", "post");
    expect(form?.querySelector('input[name="context"]')).toHaveValue("sheet");
    expect(form?.querySelector('input[name="csrfmiddlewaretoken"]')).toHaveValue(
      "token",
    );
    expect(routerPost).not.toHaveBeenCalled();
  });

  it("reopens the drawer with what was typed when the server refuses", () => {
    setPage({
      createSheet: {
        open: true,
        draft: {
          title: "Half-written notice",
          owner_office: "4",
          audience_offices: ["4"],
        },
      },
      errors: { fields: { body: ["Write the announcement body."] }, form: [] },
    });
    render(<AnnouncementAdministration />);

    const drawer = screen.getByRole("dialog");
    expect(within(drawer).getByLabelText(/^Title/)).toHaveValue("Half-written notice");
    expect(within(drawer).getByLabelText("Fairfax VA")).toBeChecked();
    expect(screen.getByText("Write the announcement body.")).toBeInTheDocument();
  });

  it("offers no create drawer without the authoring grant", () => {
    setPage({ capabilities: { canAuthor: false, canPublish: false, canPin: false } });
    render(<AnnouncementAdministration />);

    expect(
      screen.queryByRole("button", { name: /New announcement/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("refuses to render for somebody without the manage permission", () => {
    setPage();
    const { user } = pageProps.current;
    pageProps.current = {
      ...pageProps.current,
      user: user ? { ...user, permissions: [] } : null,
    };
    render(<AnnouncementAdministration />);

    expect(screen.queryByText("Office closed Monday")).not.toBeInTheDocument();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<AnnouncementAdministration />);

    expect(await axe(container)).toHaveNoViolations();
  });
});
