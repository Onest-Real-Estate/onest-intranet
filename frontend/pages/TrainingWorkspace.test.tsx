import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TrainingWorkspace from "@/pages/TrainingWorkspace";
import type {
  TrainingAdminDetail,
  TrainingDetail,
  TrainingWorkspacePageProps,
} from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as TrainingWorkspacePageProps,
}));
const routerGet = vi.hoisted(() => vi.fn());
const routerPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({
    props: pageProps.current,
    url: "/operations/training/1/edit",
  }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: routerGet, post: routerPost },
}));

const CONTENT_TYPE = {
  code: "article",
  label: "Article",
  tone: "neutral" as const,
  known: true,
};

const CATEGORY = {
  code: "compliance",
  label: "Compliance",
  tone: "neutral" as const,
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

function detail(overrides: Partial<TrainingAdminDetail> = {}): TrainingAdminDetail {
  const base: TrainingAdminDetail = {
    id: 1,
    slug: "fair-housing",
    title: "Fair housing refresher",
    summary: "Annual fair housing compliance training.",
    body: "Full text of the training.",
    lifecycle: { code: "draft", label: "Draft", tone: "neutral" },
    status: "draft",
    contentType: { code: "article", label: "Article" },
    category: { code: "compliance", label: "Compliance" },
    isRequired: true,
    versionNumber: 1,
    versionLabel: "v1",
    categoryCode: "compliance",
    contentTypeCode: "article",
    toolCode: "",
    estimatedMinutes: 30,
    externalUrl: "",
    embedUrl: "",
    displayOrder: 100,
    versionFamily: "00000000-0000-0000-0000-000000000001",
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
    validation: { isPublishable: true, items: [] },
    history: [],
    usage: {
      recipientEstimate: 0,
      completed: 0,
      inProgress: 0,
      notStarted: 0,
    },
    mediaHref: "/operations/training/1/media",
  };
  return { ...base, ...overrides };
}

function article(overrides: Partial<TrainingDetail> = {}): TrainingDetail {
  return {
    id: 1,
    slug: "fair-housing",
    title: "Fair housing refresher",
    summary: "Annual fair housing compliance training.",
    contentType: CONTENT_TYPE,
    category: CATEGORY,
    scope: { level: "office", label: "Office", officeName: "Fairfax VA" },
    isRequired: true,
    estimatedMinutes: 30,
    toolCode: null,
    completion: { status: "not_started", label: "Not started" },
    publishedAt: null,
    detailUrl: "/training-learning/1",
    body: "As a learner would read it.",
    bodyBlocks: [
      {
        type: "paragraph",
        spans: [{ type: "text", value: "As a learner would read it." }],
      },
    ],
    externalUrl: null,
    embed: null,
    primaryMedia: null,
    attachments: [],
    transcription: null,
    modules: [],
    interactivity: "unavailable",
    ...overrides,
  };
}

function setPage(overrides: Partial<TrainingWorkspacePageProps> = {}) {
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
    content: detail(),
    officeOptions: [{ value: 4, label: "Fairfax VA" }],
    categoryOptions: [{ value: "compliance", label: "Compliance" }],
    contentTypeOptions: [{ value: "article", label: "Article" }],
    toolOptions: [{ value: "lofty", label: "Lofty" }],
    audienceOptions: {
      canTargetCompany: false,
      regions: [{ value: 2, label: "Mid-Atlantic" }],
      offices: [{ value: 4, label: "Fairfax VA" }],
      roles: [{ value: "realtor", label: "Realtor" }],
    },
    capabilities: { canAuthor: true, canPublish: true },
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
  } as TrainingWorkspacePageProps;
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

describe("TrainingWorkspace", () => {
  it("refuses to render for somebody without the manage permission", () => {
    setPage();
    const { user } = pageProps.current;
    pageProps.current = {
      ...pageProps.current,
      user: user ? { ...user, permissions: [] } : null,
    };
    render(<TrainingWorkspace />);

    expect(screen.queryByLabelText(/^Title/)).not.toBeInTheDocument();
  });

  it("shows the version banner", () => {
    render(<TrainingWorkspace />);

    expect(screen.getByText("v1")).toBeInTheDocument();
    expect(screen.getByText(/Version 1 of this training item/i)).toBeInTheDocument();
  });

  it("disables publish when validation is not publishable", () => {
    setPage({
      content: detail({
        validation: {
          isPublishable: false,
          items: [
            { field: "category", message: "Choose a category before publishing." },
          ],
        },
      }),
    });
    render(<TrainingWorkspace />);

    expect(screen.getByRole("button", { name: /Publish now/ })).toBeDisabled();
    expect(screen.getByText("Choose a category before publishing.")).toBeVisible();
  });

  it("surfaces a concurrent-edit conflict", () => {
    setPage({
      errors: {
        fields: {},
        form: ["Somebody else saved this training while you were writing."],
      },
      content: detail({ title: "Their wording" }),
    });
    render(<TrainingWorkspace />);

    expect(screen.getByText(/Somebody else saved this training/i)).toBeVisible();
    expect(screen.getByLabelText(/^Title/)).toHaveValue("Their wording");
  });
});
