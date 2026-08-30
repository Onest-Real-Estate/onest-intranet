import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

const pageProps = vi.hoisted(() => ({
  current: {} as OnboardingToolCatalogPageProps,
}));
const routerPost = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/operations/tool-catalog" }),
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  Head: () => null,
  router: { post: routerPost },
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
    required: true,
    active: true,
    sortOrder: 20,
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
            provisioningLabel: "You set this up",
            steps: ["Sign in at c2ex.realtor."],
          }),
        ],
      },
    ],
    offices: [
      { value: "4", label: "Connecticut" },
      { value: "5", label: "Fairfax VA" },
    ],
    options: {
      groups: [{ value: "association", label: "Association & MLS" }],
      provisioning: [{ value: "both", label: "You sign up, then oNEST activates it" }],
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
  setPage();
});

describe("OnboardingToolCatalog", () => {
  it("summarises each row so an administrator can scan without opening it", () => {
    render(<OnboardingToolCatalog />);
    // Applicability is named in words: "not company-wide" would say nothing
    // about who actually gets the tool.
    expect(
      screen.getByText(/You sign up, then oNEST activates it · Connecticut · 2 steps/),
    ).toBeVisible();
  });

  it("says when a tool has no steps rather than leaving the reader guessing", () => {
    setPage({
      groups: [
        {
          code: "association",
          label: "Association & MLS",
          tools: [catalogTool({ steps: [] })],
        },
      ],
    });
    render(<OnboardingToolCatalog />);
    expect(screen.getByText(/no steps/)).toBeVisible();
  });

  it("opens one row's editor in place", () => {
    setPage({ editing: "smartmls" });
    render(<OnboardingToolCatalog />);
    expect(screen.getByLabelText(/^Name/)).toHaveValue("SmartMLS");
    expect(screen.getByLabelText(/^Identifier/)).toHaveValue("smartmls");
  });

  it("posts an edit to that tool's own endpoint", () => {
    setPage({ editing: "smartmls" });
    render(<OnboardingToolCatalog />);
    const form = screen.getByLabelText(/^Name/).closest("form");
    expect(form).toHaveAttribute("action", "/operations/tool-catalog/smartmls");
    expect(form).toHaveAttribute("method", "post");
  });

  it("posts a new tool to the create endpoint", () => {
    setPage({ editing: "new" });
    render(<OnboardingToolCatalog />);
    const form = screen.getByLabelText(/^Name/).closest("form");
    expect(form).toHaveAttribute("action", "/operations/tool-catalog/new");
  });

  it("edits the guide as an ordered list, not a paragraph", () => {
    setPage({ editing: "smartmls" });
    render(<OnboardingToolCatalog />);

    // Each step is its own field, so pasting a wrapped sentence cannot
    // silently become two steps.
    expect(screen.getByLabelText("Step 1")).toHaveValue("Membership must be active.");
    expect(screen.getByLabelText("Step 2")).toHaveValue("Complete onboarding.");
  });

  it("adds and removes steps", async () => {
    const user = userEvent.setup();
    setPage({ editing: "smartmls" });
    render(<OnboardingToolCatalog />);

    await user.click(screen.getByRole("button", { name: "Add step" }));
    expect(screen.getByLabelText("Step 3")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Remove step 3" }));
    expect(screen.queryByLabelText("Step 3")).toBeNull();
  });

  it("reorders steps without losing what was typed", async () => {
    const user = userEvent.setup();
    setPage({ editing: "smartmls" });
    render(<OnboardingToolCatalog />);

    await user.click(screen.getByRole("button", { name: "Move step 2 up" }));

    expect(screen.getByLabelText("Step 1")).toHaveValue("Complete onboarding.");
    expect(screen.getByLabelText("Step 2")).toHaveValue("Membership must be active.");
  });

  it("shows the office picker only for a tool that is not company-wide", () => {
    setPage({ editing: "smartmls" });
    render(<OnboardingToolCatalog />);

    const connecticut = screen.getByLabelText("Connecticut");
    expect(connecticut).toBeChecked();
    expect(screen.getByLabelText("Fairfax VA")).not.toBeChecked();
  });

  it("hides the office picker once a tool applies everywhere", async () => {
    const user = userEvent.setup();
    setPage({ editing: "smartmls" });
    render(<OnboardingToolCatalog />);

    await user.click(screen.getByLabelText("Every office"));
    expect(screen.queryByLabelText("Connecticut")).toBeNull();
  });

  it("posts the whole new order when a tool moves", async () => {
    const user = userEvent.setup();
    render(<OnboardingToolCatalog />);

    await user.click(screen.getByRole("button", { name: "Move C2EX up" }));

    // The complete intended sequence, so the server never reconstructs a move
    // from a delta it did not witness.
    expect(routerPost).toHaveBeenCalledOnce();
    expect(routerPost.mock.calls[0][0]).toBe("/operations/tool-catalog/reorder");
    expect(routerPost.mock.calls[0][1]).toMatchObject({
      group: "association",
      order: ["c2ex", "smartmls"],
    });
  });

  it("cannot move the first row up or the last row down", () => {
    render(<OnboardingToolCatalog />);
    expect(screen.getByRole("button", { name: "Move SmartMLS up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move C2EX down" })).toBeDisabled();
  });

  it("keeps the row open and the draft when a save is refused", () => {
    setPage({
      editing: "new",
      draft: { name: "Follow Up Boss", slug: "follow-up-boss" },
      errors: {
        fields: { contact_label: ["Say who to contact, or give the steps."] },
        form: [],
      },
    });
    render(<OnboardingToolCatalog />);

    expect(screen.getByLabelText(/^Name/)).toHaveValue("Follow Up Boss");
    expect(
      screen.getAllByText("Say who to contact, or give the steps.").length,
    ).toBeGreaterThan(0);
  });

  it("marks an inactive tool in words", () => {
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
    const row = screen.getByText("SmartMLS").closest("li");
    expect(within(row as HTMLElement).getByText("Inactive")).toBeVisible();
  });

  it("has no automated accessibility violations", async () => {
    setPage({ editing: "smartmls" });
    const { container } = render(<OnboardingToolCatalog />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
