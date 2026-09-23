import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

const pageProps = vi.hoisted(() => ({ current: {} as MyToolsPageProps }));
const routerPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/my-tools" }),
  Link: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: ReactNode;
    "aria-label"?: string;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
  Head: () => null,
  router: { post: routerPost },
}));

import MyTools from "@/pages/MyTools";
import type { AgentTool, MyToolsPageProps } from "@/types";

function tool(overrides: Partial<AgentTool> = {}): AgentTool {
  return {
    slug: "rpr",
    name: "RPR",
    description: "Property research, reports, and market analytics.",
    group: "company",
    provisioning: "self_serve",
    provisioningLabel: "You set this up",
    selfServe: true,
    required: true,
    openUrl: "",
    helpUrl: "https://blog.narrpr.com/support/",
    steps: ["Go to narrpr.com and choose Create Account.", "Verify with NRDS."],
    contact: "Your branch admin, for your NRDS number",
    requestPath: "",
    state: { code: "not_started", label: "Not started", tone: "neutral" },
    invitation: {
      state: "not_applicable",
      label: "You set this one up yourself",
      sentAt: null,
    },
    complete: false,
    note: "",
    updatedAt: null,
    haveIt: false,
    haveItAt: null,
    supportHref: "/support/it?tool=rpr",
    training: null,
    ...overrides,
  };
}

function setPage(overrides: Partial<MyToolsPageProps> = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "agent@onest.realestate",
      name: "Sam Agent",
      headshotUrl: null,
      permissions: [],
      roles: ["realtor"],
      roleLabel: "Agent",
      isStaff: false,
      isSuperuser: false,
    },
    csrfToken: "token",
    requestId: "r1",
    features: {},
    primaryOffice: null,
    shell: null,
    notifications: null,
    agent: { id: 1, name: "Sam Agent", office: "Connecticut", isSelf: true },
    groups: [
      {
        code: "company",
        label: "Company tools",
        tools: [tool()],
        ready: 0,
        total: 1,
      },
    ],
    readiness: { ready: 0, total: 1, percent: 0, complete: false },
    canManage: false,
    stateOptions: [
      { value: "not_started", label: "Not started" },
      { value: "ready", label: "Ready" },
    ],
    supportPath: "/support/it",
    errors: { fields: {}, form: [] },
    ...overrides,
  } as MyToolsPageProps;
}

beforeEach(() => {
  routerPost.mockClear();
  setPage();
});

function withTools(tools: AgentTool[], extra: Partial<MyToolsPageProps> = {}) {
  setPage({
    groups: [
      { code: "company", label: "Company tools", tools, ready: 0, total: tools.length },
    ],
    ...extra,
  });
}

function card(name: string): HTMLElement {
  return screen.getByRole("article", { name });
}

describe("MyTools", () => {
  it("lists each tool with what it is for", () => {
    render(<MyTools />);
    expect(screen.getByText("RPR")).toBeVisible();
    expect(
      screen.getByText("Property research, reports, and market analytics."),
    ).toBeVisible();
  });

  it("checks a tool off and posts only the agent's own mark", async () => {
    const user = userEvent.setup();
    render(<MyTools />);

    const box = screen.getByRole("checkbox", { name: "I have RPR" });
    await user.click(box);

    expect(routerPost).toHaveBeenCalledOnce();
    expect(routerPost.mock.calls[0][0]).toBe("/my-tools/rpr/have");
    expect(routerPost.mock.calls[0][1]).toEqual({ have: true });
    // The tick lands before the server answers.
    expect(box).toBeChecked();
    expect(
      screen.getByRole("progressbar", { name: "1 of 1 tools checked off" }),
    ).toHaveAttribute("aria-valuenow", "1");
  });

  it("unticks a tool the agent had checked off", async () => {
    const user = userEvent.setup();
    withTools([tool({ haveIt: true, haveItAt: "2026-09-01T12:00:00Z" })]);
    render(<MyTools />);

    await user.click(screen.getByRole("checkbox", { name: "I have RPR" }));
    expect(routerPost.mock.calls[0][1]).toEqual({ have: false });
  });

  it("clicking the tool name toggles the box", async () => {
    const user = userEvent.setup();
    render(<MyTools />);
    await user.click(screen.getByText("RPR"));
    expect(routerPost).toHaveBeenCalledOnce();
  });

  it("shows somebody else's checklist read-only, with when they ticked it", () => {
    withTools([tool({ haveIt: true, haveItAt: "2026-09-03T12:00:00Z" })], {
      agent: { id: 7, name: "Ada", office: null, isSelf: false },
    });
    render(<MyTools />);

    const box = screen.getByRole("checkbox", { name: /checked off by agent/ });
    expect(box).toBeDisabled();
    expect(box).toBeChecked();
    expect(within(card("RPR")).getByText(/Agent checked off/)).toBeVisible();
  });

  it("links the tool's training when one is linked", () => {
    withTools([
      tool({
        training: {
          href: "/training/12",
          title: "Getting started with RPR",
          minutes: 6,
          completed: false,
          inProgress: false,
        },
      }),
    ]);
    render(<MyTools />);

    const link = within(card("RPR")).getByRole("link", { name: /Training for RPR/ });
    expect(link).toHaveAttribute("href", "/training/12");
    expect(within(link).getByText("6 min")).toBeVisible();
  });

  it("offers no training button when nothing is linked", () => {
    render(<MyTools />);
    expect(within(card("RPR")).queryByRole("link", { name: /Training/ })).toBeNull();
  });

  it("sends Support straight to help for that tool", () => {
    render(<MyTools />);
    expect(
      within(card("RPR")).getByRole("link", { name: "Get support with RPR" }),
    ).toHaveAttribute("href", "/support/it?tool=rpr");
  });

  it("opens the setup steps without leaving the page", async () => {
    const user = userEvent.setup();
    render(<MyTools />);

    await user.click(screen.getByRole("button", { name: "Setup steps for RPR" }));

    const guide = await screen.findByRole("dialog");
    expect(
      within(guide).getByText("Go to narrpr.com and choose Create Account."),
    ).toBeVisible();
    expect(within(guide).getByText(/Your branch admin/)).toBeVisible();
  });

  it("shows the agent why their own tool is blocked, on the card", () => {
    withTools([
      tool({
        state: { code: "blocked", label: "Blocked", tone: "destructive" },
        note: "Waiting on the association for the NRDS number.",
      }),
    ]);
    render(<MyTools />);
    expect(
      within(card("RPR")).getByText("Waiting on the association for the NRDS number."),
    ).toBeVisible();
    expect(within(card("RPR")).getByText("Blocked")).toBeVisible();
  });

  it("keeps what oNEST confirmed apart from the agent's tick", () => {
    withTools([
      tool({ slug: "rpr", name: "RPR" }),
      tool({ slug: "lofty", name: "Lofty", selfServe: false, provisioning: "onest" }),
      tool({
        slug: "skyslope",
        name: "SkySlope",
        selfServe: false,
        complete: true,
        state: { code: "ready", label: "Ready", tone: "success" },
      }),
    ]);
    render(<MyTools />);

    // A self-serve tool nobody has touched has nothing to say beyond the box.
    expect(within(card("RPR")).queryByText(/oNEST|office/)).toBeNull();
    expect(within(card("Lofty")).getByText("Waiting on your office")).toBeVisible();
    expect(within(card("SkySlope")).getByText("Confirmed by oNEST")).toBeVisible();
    // Confirmation is not a tick: the agent still has checked off nothing.
    expect(screen.getByRole("checkbox", { name: "I have SkySlope" })).not.toBeChecked();
  });

  it("leaves optional and excused tools out of the count", () => {
    withTools([
      tool({ slug: "rpr", name: "RPR", haveIt: true }),
      tool({ slug: "facebook", name: "Facebook", required: false }),
      tool({
        slug: "smartmls",
        name: "SmartMLS",
        state: { code: "not_applicable", label: "Not needed", tone: "neutral" },
      }),
    ]);
    render(<MyTools />);

    expect(within(card("Facebook")).getByText("Optional")).toBeVisible();
    expect(screen.getByRole("checkbox", { name: "I have SmartMLS" })).toBeDisabled();
    expect(screen.getByText("You have every tool you need")).toBeVisible();
  });

  it("counts each group separately", () => {
    setPage({
      groups: [
        {
          code: "company",
          label: "Company tools",
          tools: [tool({ haveIt: true })],
          ready: 0,
          total: 1,
        },
        {
          code: "association",
          label: "Association & MLS",
          tools: [tool({ slug: "smartmls", name: "SmartMLS" })],
          ready: 0,
          total: 1,
        },
      ],
    });
    render(<MyTools />);

    const company = screen.getByRole("region", { name: "Company tools" });
    const mls = screen.getByRole("region", { name: "Association & MLS" });
    expect(within(company).getByText("1 of 1 checked off")).toBeVisible();
    expect(within(mls).getByText("0 of 1 checked off")).toBeVisible();
  });

  it("does not offer the status control to somebody who may not manage", () => {
    render(<MyTools />);
    expect(screen.queryByLabelText("oNEST status")).toBeNull();
  });

  it("offers the status control to a manager and posts the change", async () => {
    const user = userEvent.setup();
    setPage({
      canManage: true,
      agent: { id: 7, name: "Ada", office: null, isSelf: false },
    });
    render(<MyTools />);

    await user.selectOptions(screen.getByLabelText("oNEST status"), "ready");

    expect(routerPost).toHaveBeenCalledOnce();
    expect(routerPost.mock.calls[0][0]).toBe("/operations/tool-readiness/7/state");
    expect(routerPost.mock.calls[0][1]).toMatchObject({ tool: "rpr", state: "ready" });
  });

  it("lets a manager confirm a tool the agent ticked in one click", async () => {
    const user = userEvent.setup();
    withTools([tool({ haveIt: true, haveItAt: "2026-09-03T12:00:00Z" })], {
      canManage: true,
      agent: { id: 7, name: "Ada", office: null, isSelf: false },
    });
    render(<MyTools />);

    await user.click(screen.getByRole("button", { name: "Confirm ready" }));

    expect(routerPost.mock.calls[0][0]).toBe("/operations/tool-readiness/7/state");
    expect(routerPost.mock.calls[0][1]).toEqual({ tool: "rpr", state: "ready" });
  });

  it("offers no confirm button until the agent has ticked", () => {
    withTools([tool()], {
      canManage: true,
      agent: { id: 7, name: "Ada", office: null, isSelf: false },
    });
    render(<MyTools />);
    expect(screen.queryByRole("button", { name: "Confirm ready" })).toBeNull();
  });

  it("explains an empty checklist instead of showing nothing", () => {
    setPage({
      groups: [],
      readiness: { ready: 0, total: 0, percent: 100, complete: true },
    });
    render(<MyTools />);
    expect(screen.getByText("No tools to set up")).toBeVisible();
  });

  it("has no automated accessibility violations", async () => {
    withTools(
      [
        tool({
          training: {
            href: "/training/12",
            title: "RPR basics",
            minutes: 6,
            completed: true,
            inProgress: false,
          },
        }),
        tool({
          slug: "lofty",
          name: "Lofty",
          selfServe: false,
          openUrl: "https://lofty.com",
        }),
      ],
      { canManage: true },
    );
    const { container } = render(<MyTools />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
