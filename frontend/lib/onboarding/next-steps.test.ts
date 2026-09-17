import { describe, expect, it } from "vitest";

import {
  NEXT_STEP_SOURCES,
  type NextStepSource,
  nextStepItems,
} from "@/lib/onboarding/next-steps";
import {
  activationGuide,
  agentJourney,
  agentTool,
  invitedTool,
} from "@/test/onboarding";
import type { AgentActivationGuide } from "@/types";

function rows(
  tools: ReturnType<typeof agentTool>[],
  guides: Record<string, AgentActivationGuide>,
) {
  return nextStepItems({ journey: agentJourney({ tools }), guides }).filter((item) =>
    item.key.startsWith("tool-"),
  );
}

describe("tool rows", () => {
  it("offers no guide button while the invitation is only locked", () => {
    const [row] = rows([agentTool()], { lofty: { state: "locked" } });
    expect(row.actions).toEqual([]);
    expect(row.guide?.state).toBe("locked");
  });

  it("offers the activation guide once the server unlocks it", () => {
    const [row] = rows([invitedTool()], { lofty: activationGuide() });
    expect(row.actions).toEqual([
      {
        label: "Watch how to activate Lofty",
        href: "/training-learning/42",
        primary: true,
      },
    ]);
  });

  it("keeps a finished guide replayable without pressing for it again", () => {
    const [row] = rows([invitedTool()], {
      lofty: activationGuide({ state: "completed" }),
    });
    expect(row.actions).toEqual([
      { label: "Watch the Lofty guide again", href: "/training-learning/42" },
    ]);
  });

  it("one tool's invitation never unlocks another tool's guide", () => {
    const result = rows(
      [
        invitedTool({ key: "skyslope", label: "SkySlope" }),
        agentTool({ key: "lofty", label: "Lofty" }),
      ],
      {
        skyslope: activationGuide({ href: "/training-learning/7" }),
        lofty: { state: "locked" },
      },
    );
    expect(result[0].actions[0]?.label).toBe("Watch how to activate SkySlope");
    expect(result[1].actions).toEqual([]);
  });

  it("falls back to vendor help rather than a button that opens nothing", () => {
    const [row] = rows([invitedTool({ helpUrl: "https://help.lofty.com" })], {
      lofty: { state: "unavailable" },
    });
    expect(row.actions).toEqual([
      { label: "Open Lofty help", href: "https://help.lofty.com" },
    ]);
  });

  it("falls back to a support request when the vendor has no help page", () => {
    const [row] = rows([invitedTool({ helpUrl: "", requestPath: "/support/it" })], {
      lofty: { state: "unavailable" },
    });
    expect(row.actions).toEqual([{ label: "Contact IT Support", href: "/support/it" }]);
  });

  it("shows no action at all when a missing guide has nowhere to send anyone", () => {
    const [row] = rows([invitedTool({ helpUrl: "", requestPath: "" })], {
      lofty: { state: "unavailable" },
    });
    expect(row.actions).toEqual([]);
  });

  it("reads a ready tool as done", () => {
    const [row] = rows(
      [invitedTool({ state: "ready", stateLabel: "Ready", complete: true })],
      { lofty: activationGuide({ state: "completed" }) },
    );
    expect(row.state).toBe("done");
  });

  it("reads a blocked tool as needing attention", () => {
    const [row] = rows([invitedTool({ status: "blocked", statusLabel: "Blocked" })], {
      lofty: { state: "unavailable" },
    });
    expect(row.state).toBe("attention");
  });
});

describe("the rest of the list", () => {
  it("states an unavailable tool source once instead of inventing tool progress", () => {
    const items = nextStepItems({
      journey: agentJourney({ toolsSource: "unavailable" }),
      guides: {},
    });
    expect(items.map((item) => [item.key, item.state])).toEqual([
      ["office-handoff", "waiting"],
      ["contract", "waiting"],
      ["tools", "unavailable"],
    ]);
  });

  it("carries the contract's own correction path, never an invented one", () => {
    const items = nextStepItems({
      journey: agentJourney({
        contract: {
          state: "sent",
          label: "Ready for review and signature",
          detail: "Your agent contract is ready.",
          actionHref: "/my-contract",
          actionLabel: "Review and sign",
          updatedAt: null,
        },
      }),
      guides: {},
    });
    const contract = items.find((item) => item.key === "contract");
    expect(contract?.detail).toBe("Ready for review and signature");
    expect(contract?.actions).toEqual([
      { label: "Review and sign", href: "/my-contract", primary: true },
    ]);
  });

  it("gives a waiting contract nothing to press", () => {
    const contract = nextStepItems({ journey: agentJourney(), guides: {} }).find(
      (item) => item.key === "contract",
    );
    expect(contract?.state).toBe("waiting");
    expect(contract?.actions).toEqual([]);
  });

  it("surfaces server blockers as items needing attention", () => {
    const items = nextStepItems({
      journey: agentJourney({
        blockers: [{ key: "task-1", message: "Upload your W-9." }],
      }),
      guides: {},
    });
    expect(items.at(-1)).toMatchObject({
      state: "attention",
      detail: "Upload your W-9.",
    });
  });

  it("lets a later module add a source without touching the dialog", () => {
    const orientation: NextStepSource = () => [
      {
        key: "orientation",
        label: "Orientation",
        state: "waiting",
        detail: "Soon",
        actions: [],
      },
    ];
    const items = nextStepItems({ journey: agentJourney(), guides: {} }, [
      ...NEXT_STEP_SOURCES,
      orientation,
    ]);
    expect(items.at(-1)?.key).toBe("orientation");
  });
});
