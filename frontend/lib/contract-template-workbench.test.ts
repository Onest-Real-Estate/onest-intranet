import { describe, expect, it } from "vitest";

import {
  buildReadiness,
  publishBlockReason,
  type WorkbenchReadinessInput,
} from "@/lib/contract-template-workbench";

function input(overrides: Partial<WorkbenchReadinessInput> = {}) {
  return {
    hasSourcePdf: true,
    placedFieldCount: 3,
    agentFieldCount: 1,
    unsavedPrefillNames: [],
    layoutDirty: false,
    mergeRowCount: 2,
    unmappedKeys: [],
    hasPreview: true,
    previewStale: false,
    ...overrides,
  } satisfies WorkbenchReadinessInput;
}

describe("buildReadiness", () => {
  it("reports a fully prepared draft as ready", () => {
    const readiness = buildReadiness(input());
    expect(readiness.doneCount).toBe(4);
    expect(readiness.ready).toBe(true);
    expect(readiness.next).toBeNull();
    expect(publishBlockReason(readiness)).toBeNull();
  });

  it("stops at the upload stage before anything downstream can be judged", () => {
    const readiness = buildReadiness(
      input({ hasSourcePdf: false, placedFieldCount: 0, agentFieldCount: 0 }),
    );
    expect(readiness.next?.id).toBe("source");
    expect(readiness.next?.tab).toBe("details");
    expect(readiness.steps[1]?.state).toBe("todo");
    expect(readiness.steps[1]?.detail).toBe("Waiting on the PDF");
  });

  it("flags an unsaved layout as attention rather than as done", () => {
    const readiness = buildReadiness(input({ layoutDirty: true }));
    const fields = readiness.steps.find((step) => step.id === "fields");
    expect(fields?.state).toBe("attention");
    expect(fields?.detail).toBe("Unsaved layout changes");
    expect(readiness.ready).toBe(false);
  });

  it("counts unmapped hub sources and names them as the publish blocker", () => {
    const readiness = buildReadiness(
      input({ mergeRowCount: 3, unmappedKeys: ["PrefillText", "PrefillDate"] }),
    );
    const mapping = readiness.steps.find((step) => step.id === "mapping");
    expect(mapping?.state).toBe("attention");
    expect(mapping?.detail).toBe("2 of 3 still unmapped");
    expect(publishBlockReason(readiness)).toBe("Data mapped: 2 of 3 still unmapped");
  });

  it("treats a missing preview as the next step but never as a publish blocker", () => {
    const readiness = buildReadiness(input({ hasPreview: false }));
    expect(readiness.next?.id).toBe("preview");
    expect(publishBlockReason(readiness)).toBeNull();
  });

  it("marks a preview taken before the current edits as stale", () => {
    const readiness = buildReadiness(input({ previewStale: true }));
    const preview = readiness.steps.find((step) => step.id === "preview");
    expect(preview?.state).toBe("attention");
    expect(preview?.detail).toBe("Older than the current fields");
  });

  it("singularises the placed-field summary", () => {
    const readiness = buildReadiness(
      input({ placedFieldCount: 1, agentFieldCount: 1 }),
    );
    expect(readiness.steps[1]?.detail).toBe("1 field · 1 signer field");
  });
});
