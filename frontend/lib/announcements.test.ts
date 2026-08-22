import { describe, expect, it } from "vitest";

import {
  activeFilterCount,
  audienceIcon,
  audienceSummary,
  categoryPresentation,
  hasUnknownClassification,
  priorityPresentation,
  rejectedFilterMessage,
} from "@/lib/announcements";
import type {
  AnnouncementAudienceEntry,
  AnnouncementBadge,
  AnnouncementFilters,
} from "@/types";

function badge(overrides: Partial<AnnouncementBadge> = {}): AnnouncementBadge {
  return {
    code: "normal",
    label: "Normal",
    tone: "neutral",
    srLabel: "Priority: Normal",
    known: true,
    ...overrides,
  };
}

function filters(overrides: Partial<AnnouncementFilters> = {}): AnnouncementFilters {
  return { category: "", priority: "", rejected: [], ...overrides };
}

describe("priorityPresentation", () => {
  it("keeps the server's label and tone rather than re-deriving them", () => {
    const presentation = priorityPresentation(
      badge({ code: "urgent", label: "Urgent", tone: "destructive" }),
    );
    expect(presentation.label).toBe("Urgent");
    expect(presentation.tone).toBe("destructive");
  });

  it("adds a shape alongside the color for the two raised levels", () => {
    expect(priorityPresentation(badge({ code: "urgent" })).icon).toBeDefined();
    expect(priorityPresentation(badge({ code: "important" })).icon).toBeDefined();
  });

  it("leaves routine news without an icon so it does not compete", () => {
    expect(priorityPresentation(badge({ code: "normal" })).icon).toBeUndefined();
  });

  it("renders an unknown code on its fallback without inventing an icon", () => {
    const presentation = priorityPresentation(
      badge({ code: "normal", known: false, srLabel: "Priority: Normal (…)" }),
    );
    expect(presentation.label).toBe("Normal");
    expect(presentation.icon).toBeUndefined();
  });
});

describe("categoryPresentation", () => {
  it("carries the label and tone through untouched", () => {
    const presentation = categoryPresentation(
      badge({ code: "compliance_update", label: "Compliance Update", tone: "warning" }),
    );
    expect(presentation).toEqual({ label: "Compliance Update", tone: "warning" });
  });
});

describe("activeFilterCount", () => {
  it("counts only filters the reader set", () => {
    expect(activeFilterCount(filters())).toBe(0);
    expect(activeFilterCount(filters({ category: "event" }))).toBe(1);
    expect(activeFilterCount(filters({ category: "event", priority: "urgent" }))).toBe(
      2,
    );
  });

  it("does not count the rejected report as an applied filter", () => {
    expect(activeFilterCount(filters({ rejected: ["category", "priority"] }))).toBe(0);
  });
});

describe("rejectedFilterMessage", () => {
  it("says nothing when every filter was understood", () => {
    expect(rejectedFilterMessage(filters({ category: "event" }))).toBeNull();
  });

  it("names the filters that were dropped", () => {
    const message = rejectedFilterMessage(filters({ rejected: ["category"] }));
    expect(message).toContain("category");
  });

  it("names both when both were dropped", () => {
    const message = rejectedFilterMessage(
      filters({ rejected: ["category", "priority"] }),
    );
    expect(message).toContain("category and priority");
  });

  it("ignores a key that is not a real filter", () => {
    expect(rejectedFilterMessage(filters({ rejected: ["office"] }))).toBeNull();
  });
});

describe("hasUnknownClassification", () => {
  it("is true when any badge fell back", () => {
    expect(hasUnknownClassification([badge(), badge({ known: false })])).toBe(true);
    expect(hasUnknownClassification([badge(), badge()])).toBe(false);
  });
});

describe("audienceSummary", () => {
  function entry(
    overrides: Partial<AnnouncementAudienceEntry> = {},
  ): AnnouncementAudienceEntry {
    return {
      kind: "office",
      label: "Fairfax, VA",
      code: "",
      officeId: 6,
      userId: null,
      ...overrides,
    };
  }

  it("says a single audience plainly", () => {
    expect(audienceSummary([entry()])).toBe("Sent to Fairfax, VA.");
  });

  it("states the union rule when several selectors are combined", () => {
    const summary = audienceSummary([
      entry(),
      entry({ kind: "role", label: "Compliance", code: "compliance" }),
    ]);
    expect(summary).toContain("any of these 2");
    expect(summary).not.toContain("all");
  });

  it("says so when nothing is selected yet", () => {
    expect(audienceSummary([])).toBe("No audience selected yet.");
  });
});

describe("audienceIcon", () => {
  it("gives every selector kind its own icon", () => {
    const kinds = ["company", "role", "region", "office", "user"] as const;
    const icons = kinds.map((kind) => audienceIcon(kind));
    expect(new Set(icons).size).toBe(kinds.length);
  });
});
