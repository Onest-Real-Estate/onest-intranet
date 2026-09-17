import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import DocumentsWorkspace from "@/pages/DocumentsWorkspace";
import type {
  DocumentsAdminDetail,
  DocumentsDetail,
  DocumentsWorkspacePageProps,
} from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as DocumentsWorkspacePageProps,
}));
const routerGet = vi.hoisted(() => vi.fn());
const routerPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({
    props: pageProps.current,
    url: "/operations/documents/1/edit",
  }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: routerGet, post: routerPost },
}));

const CATEGORY = {
  code: "buyer",
  label: "Buyer",
  tone: "neutral",
  known: true,
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

function article(overrides: Partial<DocumentsDetail> = {}): DocumentsDetail {
  return {
    id: 1,
    key: "exclusive-buyer",
    name: "Exclusive buyer agreement",
    description: "Current approved buyer form",
    status: {
      code: "draft",
      label: "Draft",
      tone: "neutral",
      known: true,
    },
    category: CATEGORY,
    scope: {
      level: "office",
      label: "Office",
      officeName: "Fairfax VA",
      officeId: "4",
    },
    jurisdictionStateCodes: ["VA"],
    versionNumber: 1,
    versionLabel: "v1",
    effectiveAt: null,
    expiresAt: null,
    publishedAt: null,
    fileCount: 1,
    detailUrl: "/documents-forms/1",
    files: [
      {
        id: 10,
        displayName: "buyer.pdf",
        mediaType: "application/pdf",
        byteSize: 2048,
        checksum: "abc",
        url: "/operations/documents/files/10",
        isReadable: true,
      },
    ],
    superseded: false,
    ...overrides,
  };
}

function detail(overrides: Partial<DocumentsAdminDetail> = {}): DocumentsAdminDetail {
  return {
    id: 1,
    key: "exclusive-buyer",
    name: "Exclusive buyer agreement",
    description: "Current approved buyer form",
    lifecycle: { code: "draft", label: "Draft", tone: "neutral" },
    status: {
      code: "draft",
      label: "Draft",
      tone: "neutral",
      known: true,
    },
    category: CATEGORY,
    versionNumber: 1,
    versionLabel: "v1",
    ownerOffice: { id: 4, name: "Fairfax VA" },
    scope: {
      level: "office",
      label: "Office",
      officeName: "Fairfax VA",
      officeId: "4",
    },
    audience: AUDIENCE,
    jurisdictionStateCodes: ["VA"],
    effectiveAt: null,
    expiresAt: null,
    publishedAt: null,
    updatedAt: "2026-08-02T09:00:00Z",
    updatedBy: "Ada Admin",
    createdBy: "Ada Admin",
    version: "2026-08-02T09:00:00+00:00",
    categoryCode: "buyer",
    displayOrder: 100,
    validation: { isPublishable: true, items: [] },
    history: [],
    files: [
      {
        id: 10,
        displayName: "buyer.pdf",
        mediaType: "application/pdf",
        byteSize: 2048,
        checksum: "abc",
        url: "/operations/documents/files/10",
        isReadable: true,
        processingState: "ready",
        isActive: true,
        sortOrder: 0,
      },
    ],
    mediaHref: "/operations/documents/1/media",
    usage: {
      isCurrent: false,
      familyKey: "exclusive-buyer",
      versionNumber: 1,
      siblingCount: 1,
      publishedSiblingCount: 0,
      fileCount: 1,
      downloadCount: 0,
      wouldLeaveFamilyWithoutCurrent: false,
    },
    familyId: 9,
    ...overrides,
  };
}

function setPage(overrides: Partial<DocumentsWorkspacePageProps> = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "ada@onest.realestate",
      name: "Ada Admin",
      headshotUrl: null,
      permissions: [
        "web.manage_documents",
        "web.publish_documents",
        "web.retire_documents",
      ],
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
      capabilitySchemaVersion: "p1-document-version-admin-v1",
      help: { url: null },
      session: { authenticated: true },
    },
    notifications: null,
    document: detail(),
    officeOptions: [{ value: 4, label: "Fairfax VA" }],
    categoryOptions: [{ value: "buyer", label: "Buyer" }],
    audienceOptions: {
      canTargetCompany: false,
      regions: [{ value: 2, label: "Mid-Atlantic" }],
      offices: [{ value: 4, label: "Fairfax VA" }],
      roles: [{ value: "realtor", label: "Realtor" }],
    },
    capabilities: {
      canAuthor: true,
      canPublish: true,
      canRetire: true,
    },
    preview: {
      article: { ...article(), audience: AUDIENCE },
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
  } as DocumentsWorkspacePageProps;
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

describe("DocumentsWorkspace", () => {
  it("refuses to render for somebody without the manage permission", () => {
    setPage();
    const { user } = pageProps.current;
    pageProps.current = {
      ...pageProps.current,
      user: user ? { ...user, permissions: [] } : null,
    };
    render(<DocumentsWorkspace />);

    expect(screen.queryByLabelText(/^Name/)).not.toBeInTheDocument();
  });

  it("shows the version banner", () => {
    render(<DocumentsWorkspace />);

    expect(screen.getByText("v1")).toBeInTheDocument();
    expect(screen.getByText(/Version 1 of exclusive-buyer/i)).toBeInTheDocument();
  });

  it("disables publish when validation is not publishable", () => {
    setPage({
      document: detail({
        validation: {
          isPublishable: false,
          items: [
            {
              field: "files",
              message: "Upload at least one ready file before publishing.",
            },
          ],
        },
      }),
    });
    render(<DocumentsWorkspace />);

    expect(screen.getByRole("button", { name: /Publish now/ })).toBeDisabled();
    expect(
      screen.getByText("Upload at least one ready file before publishing."),
    ).toBeVisible();
  });

  it("explains that publishing needs its own grant", () => {
    setPage({
      capabilities: { canAuthor: true, canPublish: false, canRetire: false },
    });
    render(<DocumentsWorkspace />);

    expect(screen.getByRole("button", { name: /Publish now/ })).toBeDisabled();
    expect(
      screen.getByText(/Publishing, scheduling, and retirement need their own grants/i),
    ).toBeInTheDocument();
  });

  it("shows usage before retirement", async () => {
    setPage({
      document: detail({
        lifecycle: { code: "live", label: "Live", tone: "success" },
        status: {
          code: "published",
          label: "Published",
          tone: "success",
          known: true,
        },
        usage: {
          isCurrent: true,
          familyKey: "exclusive-buyer",
          versionNumber: 1,
          siblingCount: 1,
          publishedSiblingCount: 1,
          fileCount: 1,
          downloadCount: 4,
          wouldLeaveFamilyWithoutCurrent: true,
        },
      }),
    });
    render(<DocumentsWorkspace />);

    await userEvent.click(screen.getByRole("button", { name: /^Retire$/ }));
    expect(
      screen.getByText(/exclusive-buyer v1 has 1 files and 4 recorded downloads/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/leaves the family without a live form/i),
    ).toBeInTheDocument();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<DocumentsWorkspace />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
