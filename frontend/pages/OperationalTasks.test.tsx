import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import OperationalTasks from "@/pages/OperationalTasks";
import type { OperationalTasksPageProps, TaskBoardColumn, TaskRow } from "@/types";

const pageProps = vi.hoisted(() => ({ current: {} as OperationalTasksPageProps }));
const routerGet = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/operations/tasks" }),
  Link: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
  Head: () => null,
  router: { get: routerGet },
}));

function row(overrides: Partial<TaskRow> = {}): TaskRow {
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
    ...overrides,
  };
}

function setPage(overrides: Partial<OperationalTasksPageProps> = {}) {
  const rows = overrides.tasks?.items ?? [row()];
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
    tasks: {
      items: rows,
      pagination: {
        page: 1,
        pageSize: 25,
        totalItems: rows.length,
        totalPages: 1,
        hasNext: false,
        hasPrevious: false,
      },
      filters: { status: "", category: "", priority: "", assigned: "", q: "" },
      sort: null,
    },
    board: null,
    view: "list",
    filterOptions: {
      statuses: [{ value: "open", label: "Open" }],
      categories: [{ value: "bug", label: "Bug" }],
      priorities: [{ value: "high", label: "High" }],
    },
    summary: { open: 4, overdue: 1, mine: 2 },
    can: { manage: true, assign: true, comment: true },
    offices: [{ id: 1, name: "Fairfax VA" }],
    categories: [{ value: "bug", label: "Bug" }],
    createSheet: {
      open: false,
      draft: {
        office: "",
        category: "",
        title: "",
        description: "",
        priority: "",
        team: "",
        assignee: "",
        dueAt: "",
        tags: "",
      },
    },
    errors: { fields: {}, form: [] },
    ...overrides,
  } as OperationalTasksPageProps;
}

beforeEach(() => {
  routerGet.mockClear();
  setPage();
});

describe("OperationalTasks", () => {
  it("lists tasks with a link into each one", () => {
    render(<OperationalTasks />);
    expect(screen.getByRole("link", { name: "Provision CRM seat" })).toHaveAttribute(
      "href",
      "/operations/tasks/11111111-1111-1111-1111-111111111111",
    );
  });

  it("shows the scoped summary figures", () => {
    render(<OperationalTasks />);
    // These are counted server-side inside the reader's scope; the page never
    // derives a total from the rows it happens to be showing.
    // "Open" also appears as a status filter option and a table badge, so the
    // assertion is scoped to the metric tile that carries the figure.
    const tiles = screen.getAllByRole("article");
    const labelled = (label: string) =>
      tiles.find((tile) => tile.textContent?.startsWith(label));
    expect(labelled("Open")).toHaveTextContent("4");
    expect(labelled("Overdue")).toHaveTextContent("1");
    expect(labelled("Assigned to me")).toHaveTextContent("2");
  });

  it("marks an overdue task in words, not only in colour", () => {
    setPage({
      tasks: {
        ...pageProps.current.tasks,
        items: [row({ dueAt: "2026-01-01T09:00:00Z", isOverdue: true })],
      },
    });
    render(<OperationalTasks />);
    expect(screen.getByText("(overdue)")).toBeInTheDocument();
  });

  it("asks the server for the board rather than regrouping rows itself", async () => {
    const user = userEvent.setup();
    render(<OperationalTasks />);

    await user.click(screen.getByRole("button", { name: /board/i }));

    expect(routerGet).toHaveBeenCalledOnce();
    expect(routerGet.mock.calls[0][0]).toContain("view=board");
  });

  it("renders the columns the server grouped, including empty ones", () => {
    const column = (
      code: string,
      label: string,
      items: TaskRow[],
    ): TaskBoardColumn => ({
      status: { code, label, tone: "neutral", known: true },
      items,
      count: items.length,
    });
    setPage({
      view: "board",
      board: [
        column("open", "Open", [row()]),
        column("in_progress", "In progress", []),
      ],
    });
    render(<OperationalTasks />);

    const openColumn = screen.getByRole("region", { name: "Open" });
    expect(within(openColumn).getByText("Provision CRM seat")).toBeVisible();
    // An empty column stays: dropping it would make the board's shape depend
    // on the data rather than on the lifecycle.
    expect(screen.getByRole("region", { name: "In progress" })).toBeVisible();
  });

  it("hides the create action from somebody who may not manage", () => {
    setPage({ can: { manage: false, assign: false, comment: true } });
    render(<OperationalTasks />);
    expect(screen.queryByRole("button", { name: /new task/i })).toBeNull();
  });

  it("opens the create drawer and posts natively to the create route", async () => {
    const user = userEvent.setup();
    render(<OperationalTasks />);

    await user.click(screen.getByRole("button", { name: /new task/i }));

    const title = screen.getByLabelText(/^Title/);
    const form = title.closest("form");
    // A native POST, not an Inertia visit: one code path whether or not the
    // drawer carries a file, and a refusal comes back as an ordinary re-render.
    expect(form).toHaveAttribute("action", "/operations/tasks/new");
    expect(form).toHaveAttribute("method", "post");
  });

  it("offers only the offices the server scoped", async () => {
    const user = userEvent.setup();
    render(<OperationalTasks />);

    await user.click(screen.getByRole("button", { name: /new task/i }));

    const office = screen.getByLabelText(/^Owning office/);
    expect(
      within(office)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Choose an office", "Fairfax VA"]);
  });

  it("reopens the drawer with the draft when the server refused the save", () => {
    setPage({
      createSheet: {
        open: true,
        draft: {
          office: "1",
          category: "bug",
          title: "Printer will not enrol",
          description: "",
          priority: "high",
          team: "IT",
          assignee: "",
          dueAt: "",
          tags: "printer",
        },
      },
      errors: { fields: { dueAt: ["Use a date like 2026-03-14."] }, form: [] },
    });
    render(<OperationalTasks />);

    // The drawer posts natively, so anything the server does not echo is lost.
    expect(screen.getByLabelText(/^Title/)).toHaveValue("Printer will not enrol");
    // Twice on purpose: once in the summary at the top of the drawer, once
    // beside the field it belongs to.
    expect(screen.getAllByText("Use a date like 2026-03-14.")).toHaveLength(2);
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<OperationalTasks />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
