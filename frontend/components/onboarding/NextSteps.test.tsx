import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { NextSteps } from "@/components/onboarding/NextSteps";
import {
  activationGuide,
  agentJourney,
  agentTool,
  invitedTool,
} from "@/test/onboarding";
import type { AgentActivationGuide, AgentJourneyTool } from "@/types";

vi.mock("@inertiajs/react", () => ({
  Link: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

function renderNextSteps(
  tools: AgentJourneyTool[] = [],
  guides: Record<string, AgentActivationGuide> = {},
  journeyOverrides = {},
) {
  return render(
    <NextSteps
      journey={agentJourney({ tools, ...journeyOverrides })}
      guides={guides}
    />,
  );
}

describe("Outlook guidance", () => {
  it("names the inbox an invitation is sent to, and where else to look", () => {
    renderNextSteps();
    expect(
      screen.getByText(/Vendor invitations are sent to agent@onest\.realestate/),
    ).toBeVisible();
    expect(screen.getByText(/check Junk and the Other tab in Outlook/)).toBeVisible();
  });

  it("never asks for an invitation link, code, or password", () => {
    renderNextSteps();
    expect(
      screen.getByText(/Never paste an invitation link, code, or password/),
    ).toBeVisible();
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("offers a support path only once a recorded send is overdue", () => {
    renderNextSteps([], {});
    expect(screen.queryByRole("link", { name: "Contact IT Support" })).toBeNull();

    renderNextSteps(
      [],
      {},
      {
        invitationInbox: {
          email: "agent@onest.realestate",
          followUpHours: 48,
          overdue: true,
          supportHref: "/support/it",
        },
      },
    );
    expect(screen.getByText(/sent more than 48 hours ago/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Contact IT Support" })).toHaveAttribute(
      "href",
      "/support/it",
    );
  });
});

describe("activation guides", () => {
  it("shows no activation button while a tool is still waiting on its office", () => {
    renderNextSteps([agentTool()], { lofty: { state: "locked" } });
    expect(screen.queryByRole("link", { name: /Watch how to activate/ })).toBeNull();
    expect(
      screen.getByText(
        "The activation guide unlocks when your office sends the invitation.",
      ),
    ).toBeVisible();
  });

  it("opens the unlocked guide through the training route", () => {
    renderNextSteps([invitedTool()], { lofty: activationGuide() });
    expect(
      screen.getByRole("link", { name: /Watch how to activate Lofty/ }),
    ).toHaveAttribute("href", "/training-learning/42");
  });

  it("says what the guide costs before the agent commits to it", () => {
    renderNextSteps([invitedTool()], { lofty: activationGuide() });
    expect(screen.getByText("6 min · Transcript available")).toBeVisible();
  });

  it("reads a finished guide as finished, and keeps it replayable", () => {
    renderNextSteps([invitedTool()], {
      lofty: activationGuide({ state: "completed" }),
    });
    expect(screen.getByText("You finished this guide.")).toBeVisible();
    expect(
      screen.getByRole("link", { name: /Watch the Lofty guide again/ }),
    ).toBeVisible();
  });

  it("explains a missing guide instead of rendering a broken button", () => {
    renderNextSteps([invitedTool({ helpUrl: "https://help.lofty.com" })], {
      lofty: { state: "unavailable" },
    });
    expect(screen.queryByRole("link", { name: /Watch how to activate/ })).toBeNull();
    expect(screen.getByText(/No activation guide is published/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Open Lofty help" })).toHaveAttribute(
      "href",
      "https://help.lofty.com",
    );
  });

  it("keeps one tool's unlocked guide away from another tool's row", () => {
    renderNextSteps(
      [
        invitedTool({ key: "skyslope", label: "SkySlope" }),
        agentTool({ key: "lofty", label: "Lofty" }),
      ],
      {
        skyslope: activationGuide({ href: "/training-learning/7" }),
        lofty: { state: "locked" },
      },
    );
    expect(
      screen.getByRole("link", { name: /Watch how to activate SkySlope/ }),
    ).toBeVisible();
    expect(
      screen.queryByRole("link", { name: /Watch how to activate Lofty/ }),
    ).toBeNull();
  });
});

describe("accessibility", () => {
  it("has no detectable violations with a mixed set of rows", async () => {
    const { container } = renderNextSteps(
      [
        invitedTool({ key: "skyslope", label: "SkySlope" }),
        agentTool({ key: "lofty", label: "Lofty" }),
      ],
      {
        skyslope: activationGuide(),
        lofty: { state: "locked" },
      },
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
