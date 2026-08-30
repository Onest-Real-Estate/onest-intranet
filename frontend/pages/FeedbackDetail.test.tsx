import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import FeedbackDetail from "@/pages/FeedbackDetail";
import type { FeedbackDetailPageProps, FeedbackDetail as Ticket } from "@/types";

const pageProps = vi.hoisted(() => ({ current: {} as FeedbackDetailPageProps }));
const formPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", async () => {
  const React = await import("react");
  return {
    usePage: () => ({ props: pageProps.current, url: "/support/feedback/x" }),
    Link: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
      <a href={href} {...rest}>
        {children}
      </a>
    ),
    Head: () => null,
    useForm: (initial: Record<string, unknown>) => {
      const [data, setState] = React.useState<Record<string, unknown>>(initial);
      const [errors, setErrors] = React.useState<Record<string, string>>({});
      return {
        data,
        errors,
        processing: false,
        setData: (key: string, value: unknown) =>
          setState((prev: Record<string, unknown>) => ({ ...prev, [key]: value })),
        setError: (key: string, message: string) =>
          setErrors((prev: Record<string, string>) => ({ ...prev, [key]: message })),
        transform: () => {},
        reset: () => setState(initial),
        post: formPost,
      };
    },
  };
});

function ticket(overrides: Partial<Ticket> = {}): Ticket {
  return {
    id: "22222222-2222-2222-2222-222222222222",
    reference: "FB-000012",
    summary: "Contracts page will not load",
    category: { code: "bug", label: "Something is broken" },
    status: { code: "new", label: "New", tone: "info", known: true },
    priority: { code: "normal", label: "Normal", tone: "neutral", rank: 3 },
    urgency: { code: "slowing", label: "It is slowing me down" },
    submitter: { id: 3, name: "Marcus Webb" },
    assignee: null,
    office: { id: 1, name: "Fairfax VA" },
    createdAt: "2026-08-01T09:00:00Z",
    updatedAt: "2026-08-01T09:00:00Z",
    description: "It spins forever.",
    notes: [],
    screenshots: [],
    transitions: [],
    resolvedAt: null,
    closedAt: null,
    convertedTaskId: "",
    ...overrides,
  };
}

function setPage(overrides: Partial<FeedbackDetailPageProps> = {}) {
  pageProps.current = {
    user: {
      id: 3,
      email: "agent@onest.realestate",
      name: "Marcus Webb",
      headshotUrl: null,
      permissions: [],
      roles: ["realtor"],
      roleLabel: "Realtor",
      isStaff: false,
      isSuperuser: false,
    },
    csrfToken: "token",
    requestId: "request-1",
    features: {},
    primaryOffice: null,
    shell: null,
    notifications: null,
    ticket: ticket(),
    can: { triage: false, assign: false, note: false },
    assignees: [],
    priorities: [
      { value: "high", label: "High" },
      { value: "normal", label: "Normal" },
    ],
    errors: { fields: {}, form: [] },
    ...overrides,
  } as FeedbackDetailPageProps;
}

beforeEach(() => {
  formPost.mockClear();
  setPage();
});

describe("FeedbackDetail", () => {
  it("shows the submitter their report and lets them reply", () => {
    render(<FeedbackDetail />);
    expect(screen.getByText("It spins forever.")).toBeVisible();
    expect(screen.getByLabelText("Reply")).toBeVisible();
  });

  it("keeps triage controls away from a submitter", () => {
    render(<FeedbackDetail />);
    expect(screen.queryByText("Triage")).toBeNull();
    expect(screen.queryByText("Diagnostics")).toBeNull();
    // The internal channel is not even offered.
    expect(screen.queryByLabelText(/internal note/i)).toBeNull();
  });

  it("shows diagnostics only to a reader who can act on them", () => {
    setPage({
      can: { triage: true, assign: true, note: true },
      ticket: ticket({
        diagnostics: {
          pageUrl: "/contracts?page=2",
          metadata: { viewport: "1440x900" },
        },
      }),
    });
    render(<FeedbackDetail />);
    expect(screen.getByText("Diagnostics")).toBeVisible();
    expect(screen.getByText("/contracts?page=2")).toBeVisible();
  });

  it("says in words that an internal note is staff-only", () => {
    setPage({
      can: { triage: true, assign: true, note: true },
      ticket: ticket({
        notes: [
          {
            id: "n1",
            author: { id: 9, name: "Sam Staff" },
            body: "Third report this week.",
            internal: true,
            createdAt: "2026-08-02T09:00:00Z",
          },
        ],
      }),
    });
    render(<FeedbackDetail />);
    expect(screen.getByText(/not shown to the reporter/i)).toBeVisible();
  });

  it("links a screenshot at its authorizing route, never a storage path", () => {
    setPage({
      can: { triage: true, assign: true, note: true },
      ticket: ticket({
        screenshots: [
          {
            id: "s1",
            displayName: "broken.png",
            mediaType: "image/png",
            byteSize: 1024,
            width: 800,
            height: 600,
            href: "/support/feedback/22222222-2222-2222-2222-222222222222/screenshot/s1",
          },
        ],
      }),
    });
    render(<FeedbackDetail />);
    const link = screen.getByRole("link", { name: /broken\.png/ });
    expect(link).toHaveAttribute(
      "href",
      "/support/feedback/22222222-2222-2222-2222-222222222222/screenshot/s1",
    );
  });

  it("tells the submitter when support is waiting on them", () => {
    setPage({
      ticket: ticket({
        status: {
          code: "needs_info",
          label: "Waiting for your reply",
          tone: "warning",
          known: true,
        },
      }),
    });
    render(<FeedbackDetail />);
    expect(screen.getByText(/support has asked a question/i)).toBeVisible();
  });

  it("lets a triager assign, take, and prioritise a ticket", async () => {
    const user = userEvent.setup();
    setPage({
      can: { triage: true, assign: true, note: true },
      assignees: [{ id: 9, name: "Sam Staff" }],
    });
    render(<FeedbackDetail />);

    // Assignment posts on change: it is one decision, and a select plus a Save
    // button is two.
    await user.selectOptions(screen.getByLabelText("Assignee"), "9");
    expect(formPost.mock.calls.at(-1)?.[0]).toBe(
      "/operations/feedback/22222222-2222-2222-2222-222222222222/assign",
    );

    await user.click(screen.getByRole("button", { name: /take it/i }));
    expect(formPost.mock.calls.at(-1)?.[0]).toBe(
      "/operations/feedback/22222222-2222-2222-2222-222222222222/assign",
    );

    await user.selectOptions(screen.getByLabelText("Priority"), "high");
    expect(formPost.mock.calls.at(-1)?.[0]).toBe(
      "/operations/feedback/22222222-2222-2222-2222-222222222222/priority",
    );
  });

  it("keeps assignment away from a reader who may only triage", () => {
    setPage({ can: { triage: true, assign: false, note: true } });
    render(<FeedbackDetail />);
    expect(screen.queryByLabelText("Assignee")).toBeNull();
    // Priority is part of triage itself, so it stays.
    expect(screen.getByLabelText("Priority")).toBeVisible();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<FeedbackDetail />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
