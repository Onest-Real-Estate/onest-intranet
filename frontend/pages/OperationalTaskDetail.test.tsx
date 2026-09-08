import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import OperationalTaskDetail from "@/pages/OperationalTaskDetail";
import type { OperationalTaskDetailPageProps, TaskDetail } from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as OperationalTaskDetailPageProps,
}));
const formPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", async () => {
  const React = await import("react");
  return {
    usePage: () => ({ props: pageProps.current, url: "/operations/tasks/x" }),
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

function task(overrides: Partial<TaskDetail> = {}): TaskDetail {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    reference: "TSK-000001",
    title: "Provision CRM seat",
    category: { code: "tool_setup", label: "Tool setup" },
    status: { code: "open", label: "Open", tone: "neutral", known: true },
    priority: { code: "normal", label: "Normal", tone: "neutral", rank: 3 },
    office: { id: 1, name: "Fairfax VA" },
    assignee: { id: 2, name: "Avery Johnson" },
    team: "IT",
    dueAt: null,
    isOverdue: false,
    source: "manual",
    tags: [],
    createdAt: "2026-08-01T09:00:00Z",
    updatedAt: "2026-08-01T09:00:00Z",
    description: "The new agent has no seat.",
    reporter: { id: 3, name: "Marcus Webb" },
    sourceReference: "",
    relatedObject: null,
    startedAt: null,
    resolvedAt: null,
    closedAt: null,
    comments: [],
    attachments: [],
    transitions: [
      { target: "in_progress", label: "Start", requiresNote: false, tone: "info" },
    ],
    ...overrides,
  };
}

function setPage(overrides: Partial<OperationalTaskDetailPageProps> = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "staff@onest.realestate",
      name: "Sam Staff",
      headshotUrl: null,
      permissions: ["web.view_operational_tasks"],
      roles: ["it_support"],
      roleLabel: "IT Support",
      isStaff: false,
      isSuperuser: false,
    },
    csrfToken: "token",
    requestId: "request-1",
    features: {},
    primaryOffice: null,
    shell: null,
    notifications: null,
    task: task(),
    can: { manage: true, assign: true, comment: true },
    assignees: [
      { id: 1, name: "Sam Staff" },
      { id: 2, name: "Avery Johnson" },
    ],
    errors: { fields: {}, form: [] },
    ...overrides,
  } as OperationalTaskDetailPageProps;
}

beforeEach(() => {
  formPost.mockClear();
  setPage();
});

describe("OperationalTaskDetail", () => {
  it("offers only the moves the server said this actor may make", () => {
    render(<OperationalTaskDetail />);
    expect(screen.getByRole("button", { name: "Start" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Close" })).toBeNull();
  });

  it("hides the whole move panel when there is nothing this actor may do", () => {
    setPage({ task: task({ transitions: [] }) });
    render(<OperationalTaskDetail />);
    expect(screen.queryByText("Move this task")).toBeNull();
  });

  it("posts a transition to the task's own endpoint", async () => {
    const user = userEvent.setup();
    render(<OperationalTaskDetail />);

    await user.click(screen.getByRole("button", { name: "Start" }));

    expect(formPost).toHaveBeenCalledOnce();
    expect(formPost.mock.calls[0][0]).toBe(
      "/operations/tasks/11111111-1111-1111-1111-111111111111/transition",
    );
  });

  it("refuses to submit a move that needs a note without one", async () => {
    const user = userEvent.setup();
    setPage({
      task: task({
        transitions: [
          {
            target: "blocked",
            label: "Mark blocked",
            requiresNote: true,
            tone: "destructive",
          },
        ],
      }),
    });
    render(<OperationalTaskDetail />);

    await user.click(screen.getByRole("button", { name: "Mark blocked" }));

    // Caught in the client so the reader is not sent a round trip to be told
    // something the form could see. The service checks it again regardless.
    expect(formPost).not.toHaveBeenCalled();
    expect(screen.getByText(/explain the change/i)).toBeVisible();
  });

  it("says in words that an internal note is staff-only", () => {
    setPage({
      task: task({
        comments: [
          {
            id: "c1",
            author: { id: 2, name: "Avery Johnson" },
            body: "Vendor is stalling.",
            internal: true,
            createdAt: "2026-08-02T09:00:00Z",
          },
        ],
      }),
    });
    render(<OperationalTaskDetail />);
    // Colour alone would fail exactly the reader most at risk of quoting it.
    expect(screen.getByText(/not shown to the reporter/i)).toBeVisible();
  });

  it("offers the internal checkbox only to somebody who may manage", () => {
    setPage({ can: { manage: false, assign: false, comment: true } });
    render(<OperationalTaskDetail />);
    expect(screen.queryByLabelText(/internal note/i)).toBeNull();
    expect(screen.getByLabelText("Add a comment")).toBeVisible();
  });

  it("hides the comment form entirely without the comment grant", () => {
    setPage({ can: { manage: false, assign: false, comment: false } });
    render(<OperationalTaskDetail />);
    expect(screen.queryByLabelText("Add a comment")).toBeNull();
  });

  it("offers the assignee picker only to somebody who may assign", () => {
    setPage({ can: { manage: false, assign: false, comment: true } });
    render(<OperationalTaskDetail />);
    // Read-only for everybody else — the name is still shown, the control is not.
    expect(screen.queryByLabelText("Assignee")).toBeNull();
    expect(screen.getByText("Avery Johnson")).toBeVisible();
  });

  it("posts a reassignment to the task's own endpoint", async () => {
    const user = userEvent.setup();
    render(<OperationalTaskDetail />);

    await user.selectOptions(screen.getByLabelText("Assignee"), "1");

    expect(formPost).toHaveBeenCalledOnce();
    expect(formPost.mock.calls[0][0]).toBe(
      "/operations/tasks/11111111-1111-1111-1111-111111111111/assign",
    );
  });

  it("offers only the candidates the server scoped, plus unassigned", () => {
    render(<OperationalTaskDetail />);
    const options = screen.getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(["Unassigned", "Sam Staff", "Avery Johnson"]);
  });

  it("links an attachment to the authorized download route, never a storage url", () => {
    setPage({
      task: task({
        attachments: [
          {
            id: "a1",
            displayName: "server.log",
            mediaType: "text/plain",
            byteSize: 2048,
            internal: false,
            uploadedBy: { id: 2, name: "Avery Johnson" },
            createdAt: "2026-08-02T09:00:00Z",
          },
        ],
      }),
    });
    render(<OperationalTaskDetail />);

    const link = screen.getByRole("link", { name: /download/i });
    expect(link).toHaveAttribute(
      "href",
      "/operations/tasks/11111111-1111-1111-1111-111111111111/attachments/a1",
    );
  });

  it("says in words that an internal attachment is staff-only", () => {
    setPage({
      task: task({
        attachments: [
          {
            id: "a1",
            displayName: "vendor-contract.pdf",
            mediaType: "application/pdf",
            byteSize: 4096,
            internal: true,
            uploadedBy: { id: 2, name: "Avery Johnson" },
            createdAt: "2026-08-02T09:00:00Z",
          },
        ],
      }),
    });
    render(<OperationalTaskDetail />);
    // Said in words on the row itself, not only by the icon.
    expect(screen.getByText("Internal — staff only")).toBeVisible();
  });

  it("posts the upload as multipart to the attach endpoint", () => {
    render(<OperationalTaskDetail />);
    const field = screen.getByLabelText("Attach a file");
    const form = field.closest("form");

    expect(form).toHaveAttribute("enctype", "multipart/form-data");
    expect(form).toHaveAttribute(
      "action",
      "/operations/tasks/11111111-1111-1111-1111-111111111111/attachments",
    );
  });

  it("hides the upload form without the comment grant", () => {
    setPage({ can: { manage: false, assign: false, comment: false } });
    render(<OperationalTaskDetail />);
    expect(screen.queryByLabelText("Attach a file")).toBeNull();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<OperationalTaskDetail />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
