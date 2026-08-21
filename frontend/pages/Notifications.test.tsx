import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import Notifications from "@/pages/Notifications";
import type { NotificationRow, NotificationsPageProps } from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as NotificationsPageProps,
}));
const routerGet = vi.hoisted(() => vi.fn());
// The real router settles the visit and calls back; the page keeps its row
// controls disabled until it does, so the double must do the same.
const routerPost = vi.hoisted(() =>
  vi.fn((_url: string, _data: unknown, options?: { onFinish?: () => void }) => {
    options?.onFinish?.();
  }),
);

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/notifications" }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { get: routerGet, post: routerPost },
}));

function row(overrides: Partial<NotificationRow> = {}): NotificationRow {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    type: "administrative",
    typeLabel: "Administration",
    eventKey: "user.onboarding.owner_assigned",
    title: "An onboarding case was assigned to you",
    detail: "Onboarding for Jamie Rivera",
    priority: "high",
    priorityLabel: "High priority",
    mandatory: false,
    createdAt: "2026-08-21T12:00:00+00:00",
    availableAt: "2026-08-21T12:00:00+00:00",
    receivedLabel: "2 hr ago",
    expiresAt: null,
    readAt: null,
    archivedAt: null,
    read: false,
    archived: false,
    expired: false,
    action: { label: "Open onboarding case", href: "/operations/new-agents/7" },
    staleAction: false,
    staleActionNote: "",
    unavailableReason: "",
    ...overrides,
  };
}

function setPage(overrides: Partial<NotificationsPageProps> = {}) {
  const items = (overrides.notificationList?.items ?? [row()]) as NotificationRow[];
  pageProps.current = {
    user: {
      id: 1,
      email: "ada@onest.realestate",
      name: "Ada Agent",
      headshotUrl: null,
      permissions: [],
      roles: ["realtor"],
      roleLabel: "Realtor",
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
    notifications: { unreadCount: 1, mandatoryCount: 0, href: "/notifications" },
    notificationList: {
      items,
      pagination: {
        page: 1,
        pageSize: 20,
        totalItems: items.length,
        totalPages: 1,
        hasNext: false,
        hasPrevious: false,
      },
      filters: { status: "unread", type: "", priority: "" },
      sort: null,
    },
    filterOptions: {
      status: [
        { value: "unread", label: "Unread" },
        { value: "all", label: "All" },
        { value: "archived", label: "Archived" },
      ],
      type: [
        { value: "administrative", label: "Administration" },
        { value: "training", label: "Training" },
      ],
      priority: [
        { value: "critical", label: "Critical" },
        { value: "high", label: "High priority" },
      ],
    },
    summary: { unreadCount: 1, mandatoryCount: 0 },
    unreadByType: { administrative: 1 },
    errors: { fields: {}, form: [] },
    ...overrides,
  } as NotificationsPageProps;
}

beforeEach(() => {
  routerGet.mockClear();
  routerPost.mockClear();
  setPage();
});

describe("Notifications", () => {
  it("shows the title, the source-resolved detail, and the destination", () => {
    render(<Notifications />);

    expect(
      screen.getByRole("heading", { name: "An onboarding case was assigned to you" }),
    ).toBeVisible();
    expect(screen.getByText("Onboarding for Jamie Rivera")).toBeVisible();
    expect(screen.getByRole("link", { name: /Open onboarding case/ })).toHaveAttribute(
      "href",
      "/operations/new-agents/7",
    );
  });

  it("states read state in words rather than by weight alone", () => {
    setPage({
      notificationList: {
        ...pageProps.current.notificationList,
        items: [
          row(),
          row({
            id: "22222222-2222-2222-2222-222222222222",
            title: "Your ONEST account was reactivated",
            read: true,
            readAt: "2026-08-21T13:00:00+00:00",
          }),
        ],
      },
    });
    render(<Notifications />);

    const list = within(screen.getByRole("list"));
    expect(list.getByText("Unread")).toBeVisible();
    expect(list.getByText("Read")).toBeVisible();
  });

  it("explains a revoked source instead of showing a dead shortcut", () => {
    setPage({
      notificationList: {
        ...pageProps.current.notificationList,
        items: [
          row({
            detail: "",
            action: null,
            staleAction: true,
            staleActionNote: "This shortcut is no longer available.",
            unavailableReason:
              "The record this refers to is no longer available to you.",
          }),
        ],
      },
    });
    render(<Notifications />);

    expect(
      screen.getByText("The record this refers to is no longer available to you."),
    ).toBeVisible();
    expect(screen.queryByRole("link", { name: /Open onboarding case/ })).toBeNull();
    expect(screen.queryByText("Onboarding for Jamie Rivera")).toBeNull();
  });

  it("marks an expired notification as spent and offers no destination", () => {
    setPage({
      notificationList: {
        ...pageProps.current.notificationList,
        items: [
          row({
            expired: true,
            detail: "",
            action: null,
            unavailableReason: "This notification has expired.",
          }),
        ],
      },
    });
    render(<Notifications />);

    expect(screen.getByText("This notification has expired.")).toBeVisible();
    expect(screen.queryByRole("link", { name: /Open onboarding/ })).toBeNull();
  });

  it("labels a required notification and posts the action it was given", async () => {
    const user = userEvent.setup();
    setPage({
      notificationList: {
        ...pageProps.current.notificationList,
        items: [row({ mandatory: true })],
      },
    });
    render(<Notifications />);

    expect(screen.getByText("Required")).toBeVisible();
    await user.click(screen.getByRole("button", { name: /Mark read/ }));

    expect(routerPost).toHaveBeenCalledWith(
      "/notifications/11111111-1111-1111-1111-111111111111/state",
      expect.objectContaining({ action: "read", status: "unread", page: "1" }),
      expect.objectContaining({ preserveScroll: true }),
    );
  });

  it("offers unread and archive for a row that has already been read", async () => {
    const user = userEvent.setup();
    setPage({
      notificationList: {
        ...pageProps.current.notificationList,
        items: [row({ read: true, readAt: "2026-08-21T13:00:00+00:00" })],
      },
    });
    render(<Notifications />);

    await user.click(screen.getByRole("button", { name: /Mark unread/ }));
    expect(routerPost).toHaveBeenLastCalledWith(
      expect.stringContaining("/state"),
      expect.objectContaining({ action: "unread" }),
      expect.anything(),
    );

    await user.click(screen.getByRole("button", { name: /Archive/ }));
    expect(routerPost).toHaveBeenLastCalledWith(
      expect.stringContaining("/state"),
      expect.objectContaining({ action: "archive" }),
      expect.anything(),
    );
  });

  it("keeps mark-all-read available only while a sweepable unread exists", () => {
    setPage({ summary: { unreadCount: 1, mandatoryCount: 1 } });
    render(<Notifications />);
    expect(screen.getByRole("button", { name: /Mark all read/ })).toBeDisabled();
  });

  it("sweeps the unread rows when asked", async () => {
    const user = userEvent.setup();
    render(<Notifications />);

    await user.click(screen.getByRole("button", { name: /Mark all read/ }));
    expect(routerPost).toHaveBeenCalledWith(
      "/notifications/read-all",
      expect.objectContaining({ status: "unread" }),
      expect.anything(),
    );
  });

  it("surfaces a refused mutation instead of failing silently", () => {
    setPage({
      errors: {
        fields: {},
        form: ["Read this required notification before filing it away."],
      },
    });
    render(<Notifications />);

    const alert = screen.getByRole("alert");
    expect(
      within(alert).getByText("Read this required notification before filing it away."),
    ).toBeVisible();
  });

  it("explains an empty inbox differently when filters are doing the hiding", () => {
    setPage({
      notificationList: {
        ...pageProps.current.notificationList,
        items: [],
        filters: { status: "unread", type: "training", priority: "" },
        pagination: {
          page: 1,
          pageSize: 20,
          totalItems: 0,
          totalPages: 1,
          hasNext: false,
          hasPrevious: false,
        },
      },
    });
    render(<Notifications />);

    expect(
      screen.getByRole("heading", { name: "No notifications match these filters" }),
    ).toBeVisible();
  });

  it("says you are caught up when nothing is hidden", () => {
    setPage({
      notificationList: {
        ...pageProps.current.notificationList,
        items: [],
        pagination: {
          page: 1,
          pageSize: 20,
          totalItems: 0,
          totalPages: 1,
          hasNext: false,
          hasPrevious: false,
        },
      },
    });
    render(<Notifications />);

    expect(
      screen.getByRole("heading", { name: "You are all caught up" }),
    ).toBeVisible();
  });

  it("announces the size of the current result set", () => {
    render(<Notifications />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "1 notifications match the current filters",
    );
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<Notifications />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
