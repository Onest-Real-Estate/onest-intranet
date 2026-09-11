/**
 * Publish readiness for one contract template version.
 *
 * The workspace is a four-stage pipeline — upload, place, map, preview — and
 * before this module the stage a draft was actually stuck on was inferrable
 * only by reading three callouts scattered down a 2,000px page. The states are
 * derived here, once, from props the server already sends, so the header, the
 * readiness strip, and the tab badges cannot disagree about what is left to do.
 */

export type WorkbenchTabId = "document" | "mapping" | "details";

export type WorkbenchStepId = "source" | "fields" | "mapping" | "preview";

/**
 * `attention` is not a softer `todo`. It means the stage has content that is
 * wrong or unsaved — work the reader can lose — where `todo` is simply a stage
 * they have not reached yet.
 */
export type WorkbenchStepState = "done" | "attention" | "todo";

export interface WorkbenchStep {
  id: WorkbenchStepId;
  label: string;
  /** One line naming the state, or the single next move that clears it. */
  detail: string;
  state: WorkbenchStepState;
  /** Where the reader has to be to act on this stage. */
  tab: WorkbenchTabId;
}

export interface WorkbenchReadinessInput {
  hasSourcePdf: boolean;
  placedFieldCount: number;
  agentFieldCount: number;
  /** Prefill names on the page that the server has not stored yet. */
  unsavedPrefillNames: string[];
  /** Layout differs from the last saved layout. */
  layoutDirty: boolean;
  mergeRowCount: number;
  /** Saved Prefill keys with no hub source chosen. */
  unmappedKeys: string[];
  hasPreview: boolean;
  previewStale: boolean;
}

export interface WorkbenchReadiness {
  steps: WorkbenchStep[];
  doneCount: number;
  total: number;
  /** The first stage that is not `done`, or `null` when the draft is ready. */
  next: WorkbenchStep | null;
  ready: boolean;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

export function buildReadiness(input: WorkbenchReadinessInput): WorkbenchReadiness {
  const source: WorkbenchStep = {
    id: "source",
    label: "Source PDF",
    tab: "details",
    state: input.hasSourcePdf ? "done" : "todo",
    detail: input.hasSourcePdf ? "Uploaded" : "Upload a blank PDF to start",
  };

  const fields: WorkbenchStep = {
    id: "fields",
    label: "Fields placed",
    tab: "document",
    state: !input.hasSourcePdf
      ? "todo"
      : input.layoutDirty || input.unsavedPrefillNames.length > 0
        ? "attention"
        : input.placedFieldCount > 0
          ? "done"
          : "todo",
    detail: !input.hasSourcePdf
      ? "Waiting on the PDF"
      : input.layoutDirty
        ? "Unsaved layout changes"
        : input.placedFieldCount === 0
          ? "Place Prefill and Agent fields"
          : `${plural(input.placedFieldCount, "field")} · ${plural(
              input.agentFieldCount,
              "signer field",
            )}`,
  };

  const mapping: WorkbenchStep = {
    id: "mapping",
    label: "Data mapped",
    tab: "mapping",
    state:
      input.mergeRowCount === 0
        ? "todo"
        : input.unmappedKeys.length > 0
          ? "attention"
          : "done",
    detail:
      input.mergeRowCount === 0
        ? "Save Prefill fields to map them"
        : input.unmappedKeys.length > 0
          ? `${input.unmappedKeys.length} of ${input.mergeRowCount} still unmapped`
          : `All ${plural(input.mergeRowCount, "field")} mapped`,
  };

  const preview: WorkbenchStep = {
    id: "preview",
    label: "Preview",
    tab: "details",
    state: !input.hasPreview ? "todo" : input.previewStale ? "attention" : "done",
    detail: !input.hasPreview
      ? "Generate a filled sample"
      : input.previewStale
        ? "Older than the current fields"
        : "Generated from the saved fields",
  };

  const steps = [source, fields, mapping, preview];
  const doneCount = steps.filter((step) => step.state === "done").length;
  return {
    steps,
    doneCount,
    total: steps.length,
    next: steps.find((step) => step.state !== "done") ?? null,
    ready: doneCount === steps.length,
  };
}

/**
 * Why Publish is unavailable, in the reader's terms, or `null` when it is.
 *
 * The server refuses an unmapped publish with a validation error after the
 * click; saying so on the disabled control instead is the difference between a
 * rule and a trap.
 */
export function publishBlockReason(readiness: WorkbenchReadiness): string | null {
  const blocking = readiness.steps.find(
    (step) => step.id !== "preview" && step.state !== "done",
  );
  if (!blocking) return null;
  return `${blocking.label}: ${blocking.detail.toLowerCase()}`;
}
