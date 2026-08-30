import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import NotificationPreferences from "@/pages/NotificationPreferences";
import type {
  NotificationCategoryPreference,
  NotificationPreferencesPageProps,
} from "@/types";

const pageProps = vi.hoisted(() => ({
  current: {} as NotificationPreferencesPageProps,
}));
const routerPost = vi.hoisted(() =>
  vi.fn((_url: string, _data: unknown, options?: { onFinish?: () => void }) => {
    options?.onFinish?.();
  }),
);

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/notifications/preferences" }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { post: routerPost },
}));

function category(
  overrides: Partial<NotificationCategoryPreference> = {},
): NotificationCategoryPreference {
  const key = overrides.key ?? "training";
  return {
    key,
    label: "Training",
    description: "Courses assigned to you and their due dates.",
    mandatory: false,
    mandatoryReason: "",
    channels: [
      {
        key: "in_app",
        field: `in_app__${key}`,
        enabled: true,
        locked: true,
        lockedReason:
          "The notification centre is the record of what was sent to you, so it stays on.",
        defaultEnabled: true,
      },
      {
        key: "email",
        field: `email__${key}`,
        enabled: true,
        locked: false,
        lockedReason: "",
        defaultEnabled: true,
      },
    ],
    ...overrides,
  };
}

const MANDATORY = category({
  key: "account",
  label: "Your account",
  description: "Security and account-state notices about your own access.",
  mandatory: true,
  mandatoryReason:
    "Security notices about your own account cannot be turned off. If somebody changes your access, you are told.",
  channels: [
    {
      key: "in_app",
      field: "in_app__account",
      enabled: true,
      locked: true,
      lockedReason: "The notification centre is the record of what was sent to you.",
      defaultEnabled: true,
    },
    {
      key: "email",
      field: "email__account",
      enabled: true,
      locked: true,
      lockedReason:
        "Security notices about your own account cannot be turned off. If somebody changes your access, you are told.",
      defaultEnabled: true,
    },
  ],
});

function setPage(overrides: Partial<NotificationPreferencesPageProps> = {}) {
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
    notifications: { unreadCount: 0, mandatoryCount: 0, href: "/notifications" },
    notificationsHref: "/notifications",
    preferences: {
      channels: [
        {
          key: "in_app",
          label: "In the hub",
          description: "Every notification is recorded in your notification centre.",
          configurable: false,
          lockedReason:
            "The notification centre is the record of what was sent to you, so it stays on.",
        },
        {
          key: "email",
          label: "Email",
          description: "A short message to your work address.",
          configurable: true,
          lockedReason: "",
        },
      ],
      categories: [MANDATORY, category()],
      policy: {
        version: 1,
        savedVersion: 1,
        outdated: false,
        updatedAt: null,
        configurableChannels: ["email"],
      },
    },
    errors: { fields: {}, form: [] },
    ...overrides,
  } as NotificationPreferencesPageProps;
}

function cell(categoryLabel: string, channelLabel: string): HTMLElement {
  const group = screen.getByRole("group", { name: new RegExp(categoryLabel) });
  return within(group).getByRole("checkbox", { name: channelLabel });
}

beforeEach(() => {
  routerPost.mockClear();
  setPage();
});

describe("NotificationPreferences", () => {
  it("shows every channel for every category, locked ones included", () => {
    render(<NotificationPreferences />);

    expect(cell("Training", "Email")).toBeEnabled();
    expect(cell("Training", "In the hub")).toBeDisabled();
    expect(cell("Your account", "Email")).toBeDisabled();
  });

  it("says why a required notice cannot be switched off", () => {
    render(<NotificationPreferences />);

    const locked = cell("Your account", "Email");
    expect(locked).toBeChecked();
    expect(locked).toBeDisabled();
    // The reason is attached to the control, not left as nearby prose, so a
    // screen reader reaching the disabled switch is told why it is disabled.
    const described = locked.getAttribute("aria-describedby");
    expect(described).toBeTruthy();
    expect(document.getElementById(described as string)?.textContent).toContain(
      "cannot be turned off",
    );
  });

  it("keeps saving disabled until something actually changes", async () => {
    const user = userEvent.setup();
    render(<NotificationPreferences />);

    const save = screen.getByRole("button", { name: "Save settings" });
    expect(save).toBeDisabled();
    expect(screen.getByText("Your settings are up to date.")).toBeVisible();

    await user.click(cell("Training", "Email"));

    expect(save).toBeEnabled();
    expect(screen.getByText("You have unsaved changes.")).toBeVisible();
  });

  it("posts only the cells the reader may decide", async () => {
    const user = userEvent.setup();
    render(<NotificationPreferences />);

    await user.click(cell("Training", "Email"));
    await user.click(screen.getByRole("button", { name: "Save settings" }));

    expect(routerPost).toHaveBeenCalledTimes(1);
    const [url, data] = routerPost.mock.calls[0];
    expect(url).toBe("/notifications/preferences/submit");
    expect(data).toBeInstanceOf(FormData);
    expect(Object.fromEntries((data as FormData).entries())).toEqual({
      email__training: "false",
    });
  });

  it("says the catalog moved on without claiming anything was reset", () => {
    setPage({
      preferences: {
        ...pageProps.current.preferences,
        policy: {
          ...pageProps.current.preferences.policy,
          savedVersion: 1,
          version: 2,
          outdated: true,
        },
      },
    });
    render(<NotificationPreferences />);

    expect(screen.getByText(/Your existing choices are unchanged/)).toBeVisible();
  });

  it("surfaces a refused save instead of failing silently", () => {
    setPage({ errors: { fields: {}, form: ["That could not be saved."] } });
    render(<NotificationPreferences />);

    expect(screen.getByText("That could not be saved.")).toBeVisible();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<NotificationPreferences />);

    expect(await axe(container)).toHaveNoViolations();
  });
});
