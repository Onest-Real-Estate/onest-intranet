import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

const pageProps = vi.hoisted(() => ({
  current: {} as OnboardingToolCatalogPageProps,
}));
const routerPost = vi.hoisted(() => vi.fn());
const routerGet = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/operations/tool-catalog" }),
  Link: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: ReactNode;
    className?: string;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
  Head: () => null,
  router: { post: routerPost, get: routerGet },
}));

import OnboardingToolCatalog from "@/pages/OnboardingToolCatalog";
import type { CatalogTool, OnboardingToolCatalogPageProps } from "@/types";

function catalogTool(overrides: Partial<CatalogTool> = {}): CatalogTool {
  return {
    slug: "smartmls",
    name: "SmartMLS",
    description: "MLS listings, data, and market tools.",
    group: "association",
    provisioning: "both",
    provisioningLabel: "You sign up, then oNEST activates it",
    openUrl: "",
    helpUrl: "",
    steps: ["Membership must be active.", "Complete onboarding."],
    contact: "Your branch admin",
    requestPath: "",
    companyWide: false,
    appliesTo: "Connecticut",
    officeIds: [4],
    audience: [
      { id: 4, name: "Connecticut", path: "Northeast / Connecticut", active: true },
    ],
    required: true,
    active: true,
    sortOrder: 20,
    health: [],
    training: { published: 1, draft: 0, items: [], more: 0 },
    adoption: { ready: 0, blocked: 0, awaiting: 0 },
    ...overrides,
  };
}

function setPage(overrides: Partial<OnboardingToolCatalogPageProps> = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "admin@onest.realestate",
      name: "Admin",
      headshotUrl: null,
      permissions: ["web.manage_onboarding_tools"],
      roles: ["system_admin"],
      roleLabel: "System Admin",
      isStaff: true,
      isSuperuser: false,
    },
    csrfToken: "token",
    requestId: "r1",
    features: {},
    primaryOffice: null,
    shell: null,
    notifications: null,
    groups: [
      {
        code: "association",
        label: "Association & MLS",
        tools: [
          catalogTool(),
          // A deliberately different second row: an identical summary line on
          // both would make every assertion here ambiguous, and two identical
          // tools is not what a real catalog looks like anyway.
          catalogTool({
            slug: "c2ex",
            name: "C2EX",
            sortOrder: 0,
            companyWide: true,
            appliesTo: "Everywhere",
            officeIds: [],
            audience: [],
            provisioningLabel: "You set this up",
            steps: ["Sign in at c2ex.realtor."],
          }),
        ],
      },
    ],
    offices: [
      {
        value: "4",
        label: "Connecticut",
        path: "Northeast / Connecticut",
        kind: "region",
      },
      {
        value: "5",
        label: "Fairfax VA",
        path: "Mid-Atlantic / Virginia / Fairfax VA",
        kind: "branch",
      },
    ],
    options: {
      groups: [{ value: "association", label: "Association & MLS" }],
      provisioning: [{ value: "both", label: "You sign up, then oNEST activates it" }],
      show: [
        { value: "all", label: "All tools" },
        { value: "attention", label: "Needs attention" },
        { value: "active", label: "Active" },
        { value: "inactive", label: "Inactive" },
      ],
    },
    summary: { active: 2, inactive: 0, attention: 1, trained: 2, awaiting: 3 },
    filters: { q: "", show: "all" },
    canReorder: true,
    links: {
      teamReadiness: "/operations/tool-readiness",
      trainingAdmin: "/operations/training",
    },
    maxSteps: 12,
    editing: "",
    draft: {},
    errors: { fields: {}, form: [] },
    ...overrides,
  } as OnboardingToolCatalogPageProps;
}

beforeEach(() => {
  routerPost.mockClear();
  routerGet.mockClear();
  setPage();
});

function row(name: string): HTMLElement {
  return screen.getByRole("listitem", { name });
}

function lastGet() {
  return routerGet.mock.calls.at(-1) as [string, Record<string, string>];
}

describe("OnboardingToolCatalog", () => {
  it("says where each tool applies, in words", () => {
    render(<OnboardingToolCatalog />);
    expect(within(row("SmartMLS")).getByText("Connecticut")).toBeVisible();
    expect(within(row("C2EX")).getByText("Every office")).toBeVisible();
  });

  it("shows training coverage and flags a tool with none published", () => {
    setPage({
      groups: [
        {
          code: "association",
          label: "Association & MLS",
          tools: [
            catalogTool({
              training: { published: 0, draft: 2, items: [], more: 0 },
              health: [{ code: "no_training", label: "No published training" }],
            }),
          ],
        },
      ],
    });
    render(<OnboardingToolCatalog />);
    expect(within(row("SmartMLS")).getByText("None published")).toBeVisible();
    expect(within(row("SmartMLS")).getByText("2 in draft")).toBeVisible();
  });

  it("names the other gaps on the row itself", () => {
    setPage({
      groups: [
        {
          code: "association",
          label: "Association & MLS",
          tools: [
            catalogTool({
              health: [{ code: "no_open_link", label: "No link to open it" }],
            }),
          ],
        },
      ],
    });
    render(<OnboardingToolCatalog />);
    expect(within(row("SmartMLS")).getByText("No link to open it")).toBeVisible();
  });

  it("shows how the agents in reach are getting on, with ticks to confirm", () => {
    setPage({
      groups: [
        {
          code: "association",
          label: "Association & MLS",
          tools: [catalogTool({ adoption: { ready: 12, blocked: 1, awaiting: 3 } })],
        },
      ],
    });
    render(<OnboardingToolCatalog />);
    const smartmls = row("SmartMLS");
    expect(within(smartmls).getByText("12 ready")).toBeVisible();
    expect(within(smartmls).getByText("1 blocked")).toBeVisible();
    expect(
      within(smartmls).getByRole("link", { name: "3 to confirm" }),
    ).toHaveAttribute("href", "/operations/tool-readiness");
  });

  it("narrows to the rows that need attention from the summary", async () => {
    const user = userEvent.setup();
    render(<OnboardingToolCatalog />);
    await user.click(
      within(screen.getByRole("region", { name: "Catalog summary" })).getByRole(
        "button",
      ),
    );
    expect(lastGet()[1]).toEqual({ show: "attention" });
  });

  it("filters by status through the URL", async () => {
    const user = userEvent.setup();
    render(<OnboardingToolCatalog />);
    await user.click(screen.getByRole("button", { name: "Inactive" }));
    expect(lastGet()[0]).toBe("/operations/tool-catalog");
    expect(lastGet()[1]).toEqual({ show: "inactive" });
  });

  it("searches through the URL", async () => {
    const user = userEvent.setup();
    render(<OnboardingToolCatalog />);
    await user.type(
      screen.getByRole("searchbox", { name: "Search tools" }),
      "mls{Enter}",
    );
    expect(routerGet).toHaveBeenCalledWith(
      "/operations/tool-catalog",
      { q: "mls" },
      expect.objectContaining({ replace: true }),
    );
  });

  it("explains an empty filtered view and offers the way back", async () => {
    const user = userEvent.setup();
    setPage({
      filters: { q: "zzz", show: "all" },
      canReorder: false,
      groups: [{ code: "association", label: "Association & MLS", tools: [] }],
    });
    render(<OnboardingToolCatalog />);
    expect(screen.getByText("No tools match")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Show all tools" }));
    expect(lastGet()[1]).toEqual({});
  });

  it("opens the editor through the URL", async () => {
    const user = userEvent.setup();
    render(<OnboardingToolCatalog />);
    await user.click(screen.getByRole("button", { name: "Edit SmartMLS" }));
    expect(lastGet()[1]).toEqual({ edit: "smartmls" });
  });

  it("locks the identifier of a saved tool", async () => {
    setPage({ editing: "smartmls" });
    render(<OnboardingToolCatalog />);
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByDisplayValue("SmartMLS")).toBeVisible();
    expect(within(sheet).getByText("smartmls")).toBeVisible();
    expect(within(sheet).queryByLabelText(/Identifier/)).toBeNull();
  });

  it("posts an edit to that tool's own endpoint with the whole guide", async () => {
    const user = userEvent.setup();
    setPage({ editing: "smartmls" });
    render(<OnboardingToolCatalog />);
    const sheet = await screen.findByRole("dialog");

    await user.click(within(sheet).getByRole("button", { name: "Save changes" }));

    expect(routerPost).toHaveBeenCalledOnce();
    const [url, data] = routerPost.mock.calls[0];
    expect(url).toBe("/operations/tool-catalog/smartmls");
    expect(data).toMatchObject({
      slug: "smartmls",
      company_wide: false,
      offices: ["4"],
      step: ["Membership must be active.", "Complete onboarding."],
    });
  });

  it("derives a new tool's identifier from its name and posts to create", async () => {
    const user = userEvent.setup();
    setPage({ editing: "new" });
    render(<OnboardingToolCatalog />);
    const sheet = await screen.findByRole("dialog");

    await user.type(within(sheet).getByLabelText(/^Name/), "Follow Up Boss");
    expect(within(sheet).getByText("follow-up-boss")).toBeVisible();

    await user.click(within(sheet).getByRole("button", { name: "Add tool" }));
    expect(routerPost.mock.calls[0][0]).toBe("/operations/tool-catalog/new");
    expect(routerPost.mock.calls[0][1]).toMatchObject({ name: "Follow Up Boss" });
  });

  it("edits the guide as an ordered list and keeps text when reordering", async () => {
    const user = userEvent.setup();
    setPage({ editing: "smartmls" });
    render(<OnboardingToolCatalog />);
    const sheet = await screen.findByRole("dialog");

    await user.click(within(sheet).getByRole("button", { name: "Move step 2 up" }));
    expect(within(sheet).getByLabelText("Step 1")).toHaveValue("Complete onboarding.");

    await user.click(within(sheet).getByRole("button", { name: "Add step" }));
    expect(within(sheet).getByLabelText("Step 3")).toHaveValue("");

    await user.click(within(sheet).getByRole("button", { name: "Remove step 3" }));
    expect(within(sheet).queryByLabelText("Step 3")).toBeNull();
  });

  it("finds offices by their path and shows the choice as removable chips", async () => {
    const user = userEvent.setup();
    setPage({ editing: "smartmls" });
    render(<OnboardingToolCatalog />);
    const sheet = await screen.findByRole("dialog");

    await user.type(within(sheet).getByLabelText("Find an office"), "virginia");
    const list = within(sheet).getByRole("list", { name: "Offices" });
    expect(within(list).getByText("Fairfax VA")).toBeVisible();
    expect(within(list).queryByText("Connecticut")).toBeNull();

    await user.click(within(list).getByRole("checkbox"));
    const chosen = within(sheet).getByRole("list", { name: "Chosen offices" });
    expect(within(chosen).getByText("Fairfax VA")).toBeVisible();

    await user.click(
      within(chosen).getByRole("button", { name: "Remove Connecticut" }),
    );
    expect(within(chosen).queryByText("Connecticut")).toBeNull();
  });

  it("hides the office picker once a tool applies everywhere", async () => {
    const user = userEvent.setup();
    setPage({ editing: "smartmls" });
    render(<OnboardingToolCatalog />);
    const sheet = await screen.findByRole("dialog");

    await user.click(within(sheet).getByRole("checkbox", { name: /Every office/ }));
    expect(within(sheet).queryByLabelText("Find an office")).toBeNull();
  });

  it("lists the tool's training with links into the training workspace", async () => {
    setPage({
      editing: "smartmls",
      groups: [
        {
          code: "association",
          label: "Association & MLS",
          tools: [
            catalogTool({
              training: {
                published: 1,
                draft: 0,
                items: [
                  {
                    id: 9,
                    title: "Activating SmartMLS",
                    published: true,
                    href: "/operations/training/9/edit",
                  },
                ],
                more: 0,
              },
            }),
          ],
        },
      ],
    });
    render(<OnboardingToolCatalog />);
    const sheet = await screen.findByRole("dialog");
    expect(
      within(sheet).getByRole("link", { name: "Activating SmartMLS" }),
    ).toHaveAttribute("href", "/operations/training/9/edit");
    expect(within(sheet).getByText("Published")).toBeVisible();
  });

  it("keeps the sheet open with the draft and the error when a save is refused", async () => {
    setPage({
      editing: "new",
      draft: { name: "Follow Up Boss", companyWide: true },
      errors: {
        fields: { contact_label: ["Say who to contact, or give the steps."] },
        form: [],
      },
    });
    render(<OnboardingToolCatalog />);
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByDisplayValue("Follow Up Boss")).toBeVisible();
    expect(
      within(sheet).getAllByText("Say who to contact, or give the steps.").length,
    ).toBeGreaterThan(0);
  });

  it("posts the whole new order when a tool moves", async () => {
    const user = userEvent.setup();
    render(<OnboardingToolCatalog />);

    await user.click(screen.getByRole("button", { name: "Move C2EX up" }));

    expect(routerPost).toHaveBeenCalledOnce();
    expect(routerPost.mock.calls[0][0]).toBe("/operations/tool-catalog/reorder");
    expect(routerPost.mock.calls[0][1]).toEqual({
      group: "association",
      order: ["c2ex", "smartmls"],
    });
  });

  it("does not reorder a filtered list", () => {
    setPage({ canReorder: false, filters: { q: "", show: "active" } });
    render(<OnboardingToolCatalog />);
    expect(screen.getByRole("button", { name: "Move C2EX up" })).toBeDisabled();
    expect(screen.getByText(/Clear the search and filter to reorder/)).toBeVisible();
  });

  it("marks a retired tool in words", () => {
    setPage({
      groups: [
        {
          code: "association",
          label: "Association & MLS",
          tools: [catalogTool({ active: false })],
        },
      ],
    });
    render(<OnboardingToolCatalog />);
    expect(within(row("SmartMLS")).getByText("Retired")).toBeVisible();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<OnboardingToolCatalog />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
