import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
    certificates: {
      learners: [],
      eligibleCount: 0,
      issuedCount: 0,
      capped: false,
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

  it("shows the quiz editor for quiz drafts and posts to quiz save", async () => {
    const user = userEvent.setup();
    setPage({
      content: detail({
        contentType: { code: "quiz", label: "Quiz" },
        contentTypeCode: "quiz",
        title: "Fair housing quiz",
        quiz: null,
      }),
      contentTypeOptions: [
        { value: "article", label: "Article" },
        { value: "quiz", label: "Quiz" },
      ],
    });
    render(<TrainingWorkspace />);

    expect(screen.getByRole("heading", { name: "Quiz" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save quiz" })).toBeInTheDocument();

    await user.type(screen.getByLabelText(/^Prompt/), "Which is true?");
    const choiceInputs = screen.getAllByPlaceholderText("Choice text");
    await user.type(choiceInputs[0], "Correct");
    await user.type(choiceInputs[1], "Wrong");
    await user.click(screen.getByRole("button", { name: "Save quiz" }));

    expect(routerPost).toHaveBeenCalled();
    const [url, body] = routerPost.mock.calls.at(-1) ?? [];
    expect(url).toContain("/quiz/save");
    expect(body).toBeInstanceOf(FormData);
    expect(body.get("passThresholdPercent")).toBe("80");
    const questions = JSON.parse(String(body.get("questions")));
    expect(questions).toHaveLength(1);
    expect(questions[0].prompt).toBe("Which is true?");
  });

  it("shows the live session editor for live session drafts", async () => {
    const user = userEvent.setup();
    setPage({
      content: detail({
        contentType: { code: "live_session", label: "Live session" },
        contentTypeCode: "live_session",
        title: "Office hours",
        liveSession: null,
      }),
      contentTypeOptions: [
        { value: "article", label: "Article" },
        { value: "live_session", label: "Live session" },
      ],
    });
    render(<TrainingWorkspace />);

    expect(screen.getByRole("heading", { name: "Live session" })).toBeInTheDocument();
    const startsAt = screen.getByLabelText(/^Starts at/);
    await user.clear(startsAt);
    await user.type(startsAt, "2026-10-01T15:00");
    await user.click(screen.getByRole("button", { name: "Save session" }));

    expect(routerPost).toHaveBeenCalled();
    const [url, body] = routerPost.mock.calls.at(-1) ?? [];
    expect(url).toContain("/session/save");
    expect(body).toBeInstanceOf(FormData);
    expect(body.get("startsAt")).toBe("2026-10-01T15:00");
  });

  it("hides quiz save when the item is not a draft", () => {
    setPage({
      content: detail({
        status: "published",
        lifecycle: { code: "live", label: "Live", tone: "success" },
        contentType: { code: "quiz", label: "Quiz" },
        contentTypeCode: "quiz",
        quiz: {
          passThresholdPercent: 80,
          maxAttempts: null,
          feedbackPolicy: "score_only",
          questions: [
            {
              id: 1,
              prompt: "Ready?",
              choices: [
                { id: "a", label: "Yes" },
                { id: "b", label: "No" },
              ],
              correctChoiceIds: ["a"],
              sortOrder: 0,
            },
          ],
        },
      }),
    });
    render(<TrainingWorkspace />);

    expect(screen.getByRole("heading", { name: "Quiz" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save quiz" })).not.toBeInTheDocument();
  });

  it("shows certificates panel and posts Issue for a completed learner", async () => {
    const user = userEvent.setup();
    setPage({
      content: detail({
        certificates: {
          eligibleCount: 1,
          issuedCount: 0,
          capped: false,
          learners: [
            {
              id: 42,
              name: "Alex Agent",
              email: "alex@example.com",
              officeName: "Fairfax VA",
              completedAt: "2026-09-01T12:00:00Z",
              certificate: null,
            },
          ],
        },
      }),
    });
    render(<TrainingWorkspace />);

    expect(
      screen.getByRole("heading", { name: "Certificates of completion" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Alex Agent")).toBeInTheDocument();
    expect(screen.getByText("Not issued")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Issue" }));

    expect(routerPost).toHaveBeenCalledWith(
      "/operations/training/1/certificates/issue",
      { learnerId: 42 },
      expect.objectContaining({ preserveScroll: true }),
    );
  });

  it("shows Issued without an Issue button once the certificate is available", () => {
    setPage({
      content: detail({
        certificates: {
          eligibleCount: 1,
          issuedCount: 1,
          capped: false,
          learners: [
            {
              id: 42,
              name: "Alex Agent",
              email: "alex@example.com",
              officeName: "Fairfax VA",
              completedAt: "2026-09-01T12:00:00Z",
              certificate: { status: "approved", available: true },
            },
          ],
        },
      }),
    });
    render(<TrainingWorkspace />);

    expect(screen.getByText("Issued")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reissue" })).toBeInTheDocument();
  });
});
