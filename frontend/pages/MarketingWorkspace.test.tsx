import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MarketingWorkspace from "@/pages/MarketingWorkspace";
import type {
  MarketingAdminDetail,
  MarketingResourceDetail,
  MarketingWorkspacePageProps,
} from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as MarketingWorkspacePageProps,
}));
const routerGet = vi.hoisted(() => vi.fn());
const routerPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({
    props: pageProps.current,
    url: "/operations/marketing-resources/1/edit",
  }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: routerGet, post: routerPost },
}));

const ASSET_TYPE = {
  code: "logo",
  label: "Logo",
  tone: "brand",
  known: true,
};

const CATEGORY = {
  code: "logos",
  label: "Logos",
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

function detail(overrides: Partial<MarketingAdminDetail> = {}): MarketingAdminDetail {
  const base: MarketingAdminDetail = {
    id: 1,
    slug: "brand-logo",
    title: "Primary brand logo",
    description: "Approved primary mark",
    lifecycle: { code: "draft", label: "Draft", tone: "neutral" },
    status: "draft",
    assetType: ASSET_TYPE,
    category: CATEGORY,
    versionNumber: 1,
    versionLabel: "v1",
    categoryCode: "logos",
    assetTypeCode: "logo",
    displayOrder: 100,
    versionFamily: "00000000-0000-0000-0000-000000000001",
    ownerOffice: { id: 4, name: "Fairfax VA" },
    scopeLevel: "office",
    audience: AUDIENCE,
    jurisdictionStateCodes: [],
    brandCodes: [],
    publishAt: null,
    expiresAt: null,
    publishedAt: null,
    updatedAt: "2026-08-02T09:00:00Z",
    updatedBy: "Ada Admin",
    createdBy: "Ada Admin",
    version: "2026-08-02T09:00:00+00:00",
    usageInstructions: "Use on light backgrounds only.",
    validation: { isPublishable: true, items: [] },
    history: [],
    files: {
      exports: [
        {
          id: 10,
          role: "export",
          displayName: "logo.png",
          mediaType: "image/png",
          byteSize: 2048,
          width: 200,
          height: 200,
          isImage: true,
          url: "/marketing-resources/export/10",
          previewUrl: "/marketing-resources/preview/10",
          variants: {},
          isReadable: true,
          processingState: "ready",
          processingNote: "",
          isActive: true,
          checksum: "abc",
          sortOrder: 0,
        },
      ],
      sources: [
        {
          id: 11,
          role: "source",
          displayName: "logo.ai",
          mediaType: "application/postscript",
          byteSize: 4096,
          width: null,
          height: null,
          isImage: false,
          url: "/marketing-resources/source/11",
          previewUrl: "",
          variants: {},
          isReadable: true,
          processingState: "ready",
          processingNote: "",
          isActive: true,
          checksum: "def",
          sortOrder: 0,
        },
      ],
      previews: [],
    },
    mediaHref: "/operations/marketing-resources/1/media",
  };
  return { ...base, ...overrides };
}

function article(
  overrides: Partial<MarketingResourceDetail> = {},
): MarketingResourceDetail {
  return {
    id: 1,
    slug: "brand-logo",
    title: "Primary brand logo",
    description: "Approved primary mark",
    assetType: ASSET_TYPE,
    category: CATEGORY,
    scope: { level: "office", label: "Office", officeName: "Fairfax VA" },
    jurisdictionStateCodes: [],
    brandCodes: [],
    versionNumber: 1,
    versionLabel: "v1",
    previewUrl: "",
    exportCount: 1,
    publishedAt: null,
    detailUrl: "/marketing-resources/1",
    usageInstructions: "Use on light backgrounds only.",
    exports: [],
    publishAt: null,
    expiresAt: null,
    ...overrides,
  };
}

function setPage(overrides: Partial<MarketingWorkspacePageProps> = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "ada@onest.realestate",
      name: "Ada Admin",
      headshotUrl: null,
      permissions: [
        "web.manage_marketing_resources",
        "web.publish_marketing_resources",
        "web.download_marketing_sources",
      ],
      roles: ["marketing_team"],
      roleLabel: "Marketing Team",
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
    asset: detail(),
    officeOptions: [{ value: 4, label: "Fairfax VA" }],
    categoryOptions: [{ value: "logos", label: "Logos" }],
    assetTypeOptions: [{ value: "logo", label: "Logo" }],
    audienceOptions: {
      canTargetCompany: false,
      regions: [{ value: 2, label: "Mid-Atlantic" }],
      offices: [{ value: 4, label: "Fairfax VA" }],
      roles: [{ value: "realtor", label: "Realtor" }],
    },
    capabilities: {
      canAuthor: true,
      canPublish: true,
      canDownloadSources: true,
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
  } as MarketingWorkspacePageProps;
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

describe("MarketingWorkspace", () => {
  it("refuses to render for somebody without the manage permission", () => {
    setPage();
    const { user } = pageProps.current;
    pageProps.current = {
      ...pageProps.current,
      user: user ? { ...user, permissions: [] } : null,
    };
    render(<MarketingWorkspace />);

    expect(screen.queryByLabelText(/^Title/)).not.toBeInTheDocument();
  });

  it("shows the version banner", () => {
    render(<MarketingWorkspace />);

    expect(screen.getByText("v1")).toBeInTheDocument();
    expect(screen.getByText(/Version 1 of this marketing asset/i)).toBeInTheDocument();
  });

  it("shows source download controls when the capability is granted", () => {
    render(<MarketingWorkspace />);

    const sources = screen.getByLabelText("Source files");
    expect(sources).toBeInTheDocument();
    expect(within(sources).getByText("logo.ai")).toBeInTheDocument();
    expect(within(sources).getByRole("link", { name: /Source/i })).toHaveAttribute(
      "href",
      "/marketing-resources/source/11",
    );
  });

  it("hides source files when canDownloadSources is false", () => {
    setPage({
      capabilities: {
        canAuthor: true,
        canPublish: true,
        canDownloadSources: false,
      },
      asset: detail({
        files: {
          exports: detail().files.exports,
          sources: [],
          previews: [],
        },
      }),
    });
    render(<MarketingWorkspace />);

    expect(screen.queryByLabelText("Source files")).not.toBeInTheDocument();
    expect(screen.queryByText("logo.ai")).not.toBeInTheDocument();
  });

  it("disables publish when validation is not publishable", () => {
    setPage({
      asset: detail({
        validation: {
          isPublishable: false,
          items: [
            { field: "files", message: "Upload at least one ready export file." },
          ],
        },
      }),
    });
    render(<MarketingWorkspace />);

    expect(screen.getByRole("button", { name: /Publish now/ })).toBeDisabled();
    expect(screen.getByText("Upload at least one ready export file.")).toBeVisible();
  });
});
