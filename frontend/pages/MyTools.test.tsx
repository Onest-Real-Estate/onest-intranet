import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

const pageProps = vi.hoisted(() => ({ current: {} as MyToolsPageProps }));
const routerPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/my-tools" }),
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
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

describe("MyTools", () => {
  it("lists each tool with what it is for", () => {
    render(<MyTools />);
    expect(screen.getByText("RPR")).toBeVisible();
    expect(
      screen.getByText("Property research, reports, and market analytics."),
    ).toBeVisible();
  });

  it("opens the setup guide without leaving the page", async () => {
    const user = userEvent.setup();
    render(<MyTools />);

    // A dialog rather than an inline expand: a card that grows in place shoves
    // every card after it down the grid, so opening one answer would cost the
    // reader the position of every other.
    await user.click(screen.getByRole("button", { name: /How to set it up/ }));

    const guide = await screen.findByRole("dialog");
    expect(
      within(guide).getByText("Go to narrpr.com and choose Create Account."),
    ).toBeVisible();
    expect(within(guide).getByText(/Your branch admin/)).toBeVisible();
  });

  it("says who to ask for a tool oNEST provisions", async () => {
    const user = userEvent.setup();
    setPage({
      groups: [
        {
          code: "company",
          label: "Company tools",
          tools: [
            tool({
              slug: "lofty",
              name: "Lofty",
              provisioning: "onest",
              provisioningLabel: "oNEST sets this up for you",
              selfServe: false,
              steps: [],
              contact: "IT support — we create the seat",
            }),
          ],
          ready: 0,
          total: 1,
        },
      ],
    });
    render(<MyTools />);

    await user.click(screen.getByRole("button", { name: /How to set it up/ }));

    const guide = await screen.findByRole("dialog");
    expect(within(guide).getByText(/IT support — we create the seat/)).toBeVisible();
    // No empty numbered list where there are no steps.
    expect(within(guide).queryByRole("list")).toBeNull();
  });

  it("shows the agent why their own tool is blocked", async () => {
    const user = userEvent.setup();
    setPage({
      groups: [
        {
          code: "company",
          label: "Company tools",
          tools: [
            tool({
              state: { code: "blocked", label: "Blocked", tone: "destructive" },
              note: "Waiting on the association for the NRDS number.",
            }),
          ],
          ready: 0,
          total: 1,
        },
      ],
    });
    render(<MyTools />);

    await user.click(screen.getByRole("button", { name: /How to set it up/ }));

    // The reason is about them, so they see it — only the control that changes
    // it is staff-only. It leads the dialog, because it is why they opened it.
    const guide = await screen.findByRole("dialog");
    expect(
      within(guide).getByText("Waiting on the association for the NRDS number."),
    ).toBeVisible();
  });

  it("does not offer the state control to somebody who may not manage", async () => {
    const user = userEvent.setup();
    render(<MyTools />);
    await user.click(screen.getByText("RPR"));
    expect(screen.queryByLabelText("Mark as")).toBeNull();
  });

  it("offers the state control to a manager and posts the change", async () => {
    const user = userEvent.setup();
    setPage({
      canManage: true,
      agent: { id: 7, name: "Ada", office: null, isSelf: false },
    });
    render(<MyTools />);

    await user.click(screen.getByText("RPR"));
    await user.selectOptions(screen.getByLabelText("Mark as"), "ready");

    expect(routerPost).toHaveBeenCalledOnce();
    expect(routerPost.mock.calls[0][0]).toBe("/operations/tool-readiness/7/state");
    expect(routerPost.mock.calls[0][1]).toMatchObject({ tool: "rpr", state: "ready" });
  });

  it("marks an optional tool in words so the count reads honestly", () => {
    setPage({
      groups: [
        {
          code: "marketing",
          label: "Profiles & marketing",
          tools: [tool({ slug: "facebook", name: "Facebook", required: false })],
          // Optional tools are excluded from the denominator, which would look
          // like a bug without the label.
          ready: 0,
          total: 0,
        },
      ],
    });
    render(<MyTools />);
    expect(screen.getByText("Optional")).toBeVisible();
  });

  it("reports readiness as a labelled progress bar", () => {
    setPage({ readiness: { ready: 5, total: 21, percent: 24, complete: false } });
    render(<MyTools />);

    const bar = screen.getByRole("progressbar", { name: /5 of 21/ });
    expect(bar).toHaveAttribute("aria-valuenow", "24");
    expect(screen.getByText("24%")).toBeVisible();
  });

  it("says so plainly when everything is set up", () => {
    setPage({ readiness: { ready: 4, total: 4, percent: 100, complete: true } });
    render(<MyTools />);
    expect(screen.getByText("Everything is set up")).toBeVisible();
  });

  it("counts each group separately so a reader can see which shelf is behind", () => {
    setPage({
      groups: [
        {
          code: "company",
          label: "Company tools",
          tools: [tool()],
          ready: 3,
          total: 9,
        },
        {
          code: "association",
          label: "Association & MLS",
          tools: [tool({ slug: "smartmls", name: "SmartMLS" })],
          ready: 0,
          total: 7,
        },
      ],
    });
    render(<MyTools />);

    expect(screen.getByText("Company tools")).toBeVisible();
    expect(screen.getByText("3 of 9 ready")).toBeVisible();
    expect(screen.getByText("Association & MLS")).toBeVisible();
    expect(screen.getByText("0 of 7 ready")).toBeVisible();
  });

  it("names what the accent means, so it reads as a filter not decoration", () => {
    setPage({
      readiness: { ready: 1, total: 4, percent: 25, complete: false },
      groups: [
        {
          code: "company",
          label: "Company tools",
          tools: [
            tool({ slug: "rpr", selfServe: true }),
            tool({ slug: "onedrive", selfServe: true }),
            tool({ slug: "lofty", selfServe: false }),
            tool({ slug: "skyslope", selfServe: false, complete: true }),
          ],
          ready: 1,
          total: 4,
        },
      ],
    });
    render(<MyTools />);

    expect(screen.getByText("2 you can set up now")).toBeVisible();
    // The finished tool is excluded: whose move it was is moot once it is done.
    expect(screen.getByText("1 waiting on oNEST")).toBeVisible();
  });

  it("drops the split once everything is set up", () => {
    setPage({ readiness: { ready: 4, total: 4, percent: 100, complete: true } });
    render(<MyTools />);
    expect(screen.queryByText(/you can set up now/)).toBeNull();
  });

  it("marks your move with a glyph, not a tint", () => {
    setPage({
      groups: [
        {
          code: "company",
          label: "Company tools",
          tools: [
            tool({ slug: "rpr", name: "RPR", selfServe: true }),
            tool({
              slug: "onedrive",
              name: "OneDrive",
              selfServe: true,
              complete: true,
              state: { code: "ready", label: "Ready", tone: "success" },
            }),
          ],
          ready: 1,
          total: 2,
        },
      ],
    });
    render(<MyTools />);

    // Most of this catalog is self-serve, so tinting "your move" lit up two
    // thirds of the page. The accent stays in the header count where it is
    // rare; the cards carry the distinction as a glyph instead.
    const outstanding = screen.getByText("RPR").closest("article");
    const done = screen.getByText("OneDrive").closest("article");

    expect(
      within(outstanding as HTMLElement).getByText("You set this up"),
    ).toBeVisible();
    expect(within(done as HTMLElement).getByText("You set this up")).toBeVisible();
    // No card-level accent competing with the state marks.
    expect((outstanding as HTMLElement).querySelectorAll(".text-info").length).toBe(0);
  });

  it("has no automated accessibility violations", async () => {
    setPage({ canManage: true });
    const { container } = render(<MyTools />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
