import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import AnnouncementWorkspace from "@/pages/AnnouncementWorkspace";
import type {
  AnnouncementAdminDetail,
  AnnouncementDetail,
  AnnouncementWorkspacePageProps,
} from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as AnnouncementWorkspacePageProps,
}));
const routerGet = vi.hoisted(() => vi.fn());
const routerPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({
    props: pageProps.current,
    url: "/operations/announcements/1/edit",
  }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: routerGet, post: routerPost },
}));

const CATEGORY = {
  code: "office_notice",
  label: "Office Notice",
  tone: "neutral" as const,
  srLabel: "Category: Office Notice",
  known: true,
};

const PRIORITY = {
  code: "normal",
  label: "Normal",
  tone: "neutral" as const,
  srLabel: "Priority: Normal",
  known: true,
  rank: 30,
};

const AUDIENCE = [
  {
    kind: "office" as const,
    label: "Fairfax VA",
    code: "",
    officeId: 4,
    userId: null,
  },
];

function detail(
  overrides: Partial<AnnouncementAdminDetail> = {},
): AnnouncementAdminDetail {
  return {
    id: 1,
    slug: "office-closed",
    title: "Office closed Monday",
    summary: "The Fairfax office is closed for the holiday.",
    body: "Full text of the notice.",
    lifecycle: { code: "draft", label: "Draft", tone: "neutral" },
    status: "draft",
    category: CATEGORY,
    priority: PRIORITY,
    categoryCode: "office_notice",
    priorityCode: "normal",
    isPinned: false,
    ownerOffice: { id: 4, name: "Fairfax VA" },
    scopeLevel: "office",
    audience: AUDIENCE,
    publishAt: null,
    expiresAt: null,
    publishedAt: null,
    updatedAt: "2026-08-02T09:00:00Z",
    updatedBy: "Ada Admin",
    createdBy: "Ada Admin",
    version: "2026-08-02T09:00:00+00:00",
    cta: null,
    validation: { isPublishable: true, items: [] },
    history: [
      {
        id: "evt-1",
        action: "announcement.created",
        label: "Draft created",
        tone: "neutral",
        actor: "Ada Admin",
        occurredAt: "2026-08-01T08:00:00Z",
      },
    ],
    mediaHref: "/operations/announcements/1/media",
    ...overrides,
  };
}

/**
 * The preview payload is built by the server from the *saved* row, so its body
 * is deliberately distinct from the form's here — asserting on it proves the
 * preview panel renders the server's article and not the textarea's contents.
 */
function article(overrides: Partial<AnnouncementDetail> = {}): AnnouncementDetail {
  return {
    id: 1,
    slug: "office-closed",
    title: "Office closed Monday",
    summary: "The Fairfax office is closed for the holiday.",
    body: "As a recipient would read it.",
    publishedAt: null,
    expiresAt: null,
    category: CATEGORY,
    priority: PRIORITY,
    scope: { level: "office", label: "Office", officeName: "Fairfax VA" },
    isPinned: false,
    cta: null,
    audience: AUDIENCE,
    hero: null,
    attachments: [],
    ...overrides,
  };
}

function setPage(overrides: Partial<AnnouncementWorkspacePageProps> = {}) {
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
    announcement: detail(),
    officeOptions: [{ value: 4, label: "Fairfax VA" }],
    categoryOptions: [{ value: "office_notice", label: "Office Notice" }],
    priorityOptions: [{ value: "normal", label: "Normal" }],
    audienceOptions: {
      canTargetCompany: false,
      regions: [{ value: 2, label: "Mid-Atlantic" }],
      offices: [{ value: 4, label: "Fairfax VA" }],
      roles: [{ value: "realtor", label: "Realtor" }],
    },
    capabilities: { canAuthor: true, canPublish: true, canPin: true },
    preview: {
      article: article(),
      reach: {
        chosen: true,
        matched: true,
        officeId: 4,
        officeName: "Fairfax VA",
        roleCode: "",
        hasNamedRecipients: false,
      },
      roleCode: "",
      officeId: 4,
    },
    errors: { fields: {}, form: [] },
    posted: null,
    ...overrides,
  } as AnnouncementWorkspacePageProps;
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
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ results: [] }) }),
    ),
  );
  setPage();
});

describe("AnnouncementWorkspace", () => {
  it("loads the stored draft into the form", () => {
    render(<AnnouncementWorkspace />);

    expect(screen.getByLabelText(/^Title/)).toHaveValue("Office closed Monday");
    expect(screen.getByLabelText(/^Body/)).toHaveValue("Full text of the notice.");
    expect(screen.getByLabelText("Fairfax VA")).toBeChecked();
  });

  it("saves a draft with the version token attached", async () => {
    render(<AnnouncementWorkspace />);

    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(routerPost).toHaveBeenCalledWith(
      "/operations/announcements/1/save",
      expect.any(FormData),
      expect.anything(),
    );
    const body = bodyOf(routerPost.mock.calls[0]);
    expect(body.title).toEqual(["Office closed Monday"]);
    expect(body.expected_version).toEqual(["2026-08-02T09:00:00+00:00"]);
    // Multi-valued audience fields repeat their key, which is what
    // Django's getlist() reads.
    expect(body.audience_offices).toEqual(["4"]);
  });

  it("says plainly that saving does not notify anybody", () => {
    render(<AnnouncementWorkspace />);

    expect(screen.getByText(/Nobody is notified until it is published/i)).toBeVisible();
  });

  it("confirms before a publish rather than sending on one click", async () => {
    render(<AnnouncementWorkspace />);

    await userEvent.click(screen.getByRole("button", { name: /Publish now/ }));

    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/becomes readable immediately/i),
    ).toBeInTheDocument();
    expect(routerPost).not.toHaveBeenCalled();

    await userEvent.click(within(dialog).getByRole("button", { name: "Publish" }));

    expect(routerPost).toHaveBeenCalledWith(
      "/operations/announcements/1/lifecycle",
      expect.any(FormData),
      expect.anything(),
    );
    expect(bodyOf(routerPost.mock.calls[0])).toEqual({
      action: ["publish"],
      expected_version: ["2026-08-02T09:00:00+00:00"],
    });
  });

  it("offers only the transitions that apply to the current state", () => {
    setPage({
      announcement: detail({
        status: "archived",
        lifecycle: { code: "archived", label: "Archived", tone: "neutral" },
      }),
    });
    render(<AnnouncementWorkspace />);

    expect(screen.getByRole("button", { name: /Restore as draft/ })).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /Publish now/ }),
    ).not.toBeInTheDocument();
  });

  it("hides every lifecycle control from an author without the publish grant", () => {
    setPage({
      capabilities: { canAuthor: true, canPublish: false, canPin: false },
    });
    render(<AnnouncementWorkspace />);

    expect(screen.getByRole("button", { name: "Save changes" })).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /Publish now/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/need the publication grant/i)).toBeVisible();
  });

  it("lists what is still outstanding before the notice can go out", () => {
    setPage({
      announcement: detail({
        validation: {
          isPublishable: false,
          items: [
            { field: "body", message: "Write the announcement body." },
            { field: "priority", message: "Choose a priority before publishing." },
          ],
        },
      }),
    });
    render(<AnnouncementWorkspace />);

    expect(screen.getByText("Write the announcement body.")).toBeVisible();
    expect(screen.getByText("Choose a priority before publishing.")).toBeVisible();
  });

  it("previews the draft through the reader-facing renderer", () => {
    render(<AnnouncementWorkspace />);

    expect(screen.getByText("As a recipient would read it.")).toBeVisible();
    expect(
      screen.getByText("This reader would receive the announcement."),
    ).toBeVisible();
  });

  it("reports a reader the audience does not reach", () => {
    setPage({
      preview: {
        article: article(),
        reach: {
          chosen: true,
          matched: false,
          officeId: 9,
          officeName: "Harrisburg",
          roleCode: "",
          hasNamedRecipients: false,
        },
        roleCode: "",
        officeId: 9,
      },
    });
    render(<AnnouncementWorkspace />);

    expect(
      screen.getByText("This reader would not receive the announcement."),
    ).toBeVisible();
  });

  it("changes the previewed reader through the URL, not in the browser", async () => {
    render(<AnnouncementWorkspace />);

    await userEvent.click(screen.getByLabelText("Preview as role"));
    await userEvent.click(await screen.findByRole("option", { name: "Realtor" }));

    expect(routerGet).toHaveBeenCalledWith(
      "/operations/announcements/1/edit",
      expect.objectContaining({ previewRole: "realtor" }),
      expect.objectContaining({ replace: true }),
    );
  });

  it("surfaces a concurrent-edit conflict rather than losing the typing", () => {
    setPage({
      errors: {
        fields: {},
        form: ["Somebody else saved this announcement while you were writing."],
      },
      announcement: detail({ title: "Their wording" }),
    });
    render(<AnnouncementWorkspace />);

    expect(screen.getByText(/Somebody else saved this announcement/i)).toBeVisible();
    expect(screen.getByLabelText(/^Title/)).toHaveValue("Their wording");
  });

  it("shows the publication history from the audit trail", () => {
    render(<AnnouncementWorkspace />);

    expect(screen.getByText("Draft created")).toBeVisible();
  });

  it("warns when the actor may not address the whole brokerage", () => {
    render(<AnnouncementWorkspace />);

    expect(
      screen.getByText(/Only a brokerage-wide administrator can address everyone/i),
    ).toBeVisible();
  });

  it("refuses to render for somebody without the manage permission", () => {
    setPage();
    const { user } = pageProps.current;
    pageProps.current = {
      ...pageProps.current,
      user: user ? { ...user, permissions: [] } : null,
    };
    render(<AnnouncementWorkspace />);

    expect(screen.queryByLabelText(/^Title/)).not.toBeInTheDocument();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<AnnouncementWorkspace />);

    expect(await axe(container)).toHaveNoViolations();
  });
});
