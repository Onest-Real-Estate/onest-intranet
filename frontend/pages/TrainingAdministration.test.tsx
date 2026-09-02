import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TrainingAdministration from "@/pages/TrainingAdministration";
import type { TrainingAdministrationPageProps, TrainingAdminRow } from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as TrainingAdministrationPageProps,
}));
const routerGet = vi.hoisted(() => vi.fn());
const routerPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/operations/training" }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: routerGet, post: routerPost },
}));

function row(overrides: Partial<TrainingAdminRow> = {}): TrainingAdminRow {
  return {
    id: 1,
    slug: "fair-housing",
    title: "Fair housing refresher",
    summary: "Annual fair housing compliance training.",
    lifecycle: { code: "live", label: "Live", tone: "success" },
    status: "published",
    contentType: { code: "article", label: "Article" },
    category: { code: "compliance", label: "Compliance" },
    isRequired: true,
    versionNumber: 1,
    versionLabel: "v1",
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

function setPage(overrides: Partial<TrainingAdministrationPageProps> = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "ada@onest.realestate",
      name: "Ada Admin",
      headshotUrl: null,
      permissions: ["web.manage_training"],
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
    trainings: {
      items: [row()],
      pagination: {
        page: 1,
        pageSize: 20,
        totalItems: 1,
        totalPages: 1,
        hasNext: false,
        hasPrevious: false,
      },
      filters: {
        q: "",
        lifecycle: "",
        category: "",
        type: "",
        audience: "",
        author: "",
        office: "",
        required: "",
        publishedFrom: "",
        publishedTo: "",
      },
      sort: { key: "updatedAt", direction: "desc" },
    },
    filterOptions: {
      categories: [{ value: "compliance", label: "Compliance" }],
      contentTypes: [{ value: "article", label: "Article" }],
      offices: [{ value: 4, label: "Fairfax VA" }],
    },
    createOptions: {
      offices: [{ value: 4, label: "Fairfax VA" }],
      categories: [{ value: "compliance", label: "Compliance" }],
      contentTypes: [{ value: "article", label: "Article" }],
      tools: [{ value: "lofty", label: "Lofty" }],
      audience: {
        canTargetCompany: false,
        regions: [{ value: 2, label: "Mid-Atlantic" }],
        offices: [{ value: 4, label: "Fairfax VA" }],
        roles: [{ value: "realtor", label: "Realtor" }],
      },
    },
    createSheet: null,
    capabilities: { canAuthor: true, canPublish: true },
    errors: { fields: {}, form: [] },
    ...overrides,
  } as TrainingAdministrationPageProps;
}

beforeEach(() => {
  routerGet.mockClear();
  routerPost.mockClear();
  setPage();
});

describe("TrainingAdministration", () => {
  it("refuses to render for somebody without the manage permission", () => {
    setPage();
    const { user } = pageProps.current;
    pageProps.current = {
      ...pageProps.current,
      user: user ? { ...user, permissions: [] } : null,
    };
    render(<TrainingAdministration />);

    expect(screen.queryByText("Fair housing refresher")).not.toBeInTheDocument();
  });

  it("narrows the list through filter keys in the URL", async () => {
    render(<TrainingAdministration />);

    await userEvent.click(screen.getByLabelText("Filter by content type"));
    await userEvent.click(await screen.findByRole("option", { name: "Article" }));

    expect(routerGet).toHaveBeenCalledWith(
      "/operations/training",
      expect.objectContaining({ type: "article", page: 1 }),
      expect.objectContaining({ replace: true }),
    );
  });

  it("lists training items in scope", () => {
    render(<TrainingAdministration />);

    expect(screen.getByText("Fair housing refresher")).toBeInTheDocument();
    expect(screen.getByText("v1")).toBeInTheDocument();
  });
});
