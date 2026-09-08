import { describe, expect, it } from "vitest";

import {
  activeFilterCount,
  audienceIcon,
  audienceSummary,
  categoryPresentation,
  fileRejectionReason,
  formatBytes,
  hasBlockingMedia,
  hasUnknownClassification,
  heroSources,
  priorityPresentation,
  processingPresentation,
  rejectedFilterMessage,
} from "@/lib/announcements";
import type {
  AnnouncementAudienceEntry,
  AnnouncementBadge,
  AnnouncementFilters,
  AnnouncementMedia,
  AnnouncementMediaAdmin,
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

describe("heroSources", () => {
  const hero: AnnouncementMedia = {
    id: 9,
    role: "hero",
    displayName: "hero.png",
    mediaType: "image/png",
    byteSize: 500_000,
    width: 1600,
    height: 900,
    isImage: true,
    url: "/announcements/media/9",
    variants: {
      thumb: "/announcements/media/9/thumb",
      card: "/announcements/media/9/card",
      hero: "/announcements/media/9/hero",
    },
  };

  it("prefers the largest variant and offers the rest as srcset", () => {
    const sources = heroSources(hero);
    expect(sources?.src).toBe("/announcements/media/9/hero");
    expect(sources?.srcSet).toContain("320w");
    expect(sources?.srcSet).toContain("768w");
  });

  it("falls back to the original when processing produced no variants", () => {
    const sources = heroSources({ ...hero, variants: {} });
    expect(sources?.src).toBe("/announcements/media/9");
    expect(sources?.srcSet).toBeUndefined();
  });

  it("returns nothing when there is no hero, so the caller renders text only", () => {
    expect(heroSources(null)).toBeNull();
    expect(heroSources(undefined)).toBeNull();
  });

  it("refuses a non-image, which could never render as a hero", () => {
    expect(heroSources({ ...hero, isImage: false })).toBeNull();
  });

  it("ignores a variant label the server does not generate", () => {
    const sources = heroSources({
      ...hero,
      variants: { ...hero.variants, bogus: "/announcements/media/9/bogus" },
    });
    expect(sources?.srcSet).not.toContain("bogus");
  });
});

describe("fileRejectionReason", () => {
  const limits = { extensions: [".pdf", ".png"], maxBytes: 1024 };

  it("names a type that is not allowed", () => {
    const reason = fileRejectionReason({ name: "x.exe", size: 10 }, limits);
    expect(reason).toContain(".exe");
  });

  it("names the size limit", () => {
    const reason = fileRejectionReason({ name: "x.pdf", size: 2048 }, limits);
    expect(reason).toContain("1 KB");
  });

  it("accepts an allowed file, letting the server make the real decision", () => {
    expect(fileRejectionReason({ name: "x.pdf", size: 100 }, limits)).toBeNull();
  });

  it("is case-insensitive about the extension", () => {
    expect(fileRejectionReason({ name: "X.PDF", size: 100 }, limits)).toBeNull();
  });
});

describe("hasBlockingMedia", () => {
  function admin(state: AnnouncementMediaAdmin["processingState"]) {
    return { processingState: state } as AnnouncementMediaAdmin;
  }

  it("blocks while anything is unfinished or rejected", () => {
    expect(hasBlockingMedia([admin("ready"), admin("pending")])).toBe(true);
    expect(hasBlockingMedia([admin("quarantined")])).toBe(true);
    expect(hasBlockingMedia([admin("failed")])).toBe(true);
  });

  it("does not block when everything passed", () => {
    expect(hasBlockingMedia([admin("ready"), admin("ready")])).toBe(false);
    expect(hasBlockingMedia([])).toBe(false);
  });
});

describe("processingPresentation", () => {
  it("gives failure states a destructive tone and success a positive one", () => {
    expect(processingPresentation("quarantined").tone).toBe("destructive");
    expect(processingPresentation("failed").tone).toBe("destructive");
    expect(processingPresentation("ready").tone).toBe("success");
  });

  it("always carries a readable label, never tone alone", () => {
    for (const state of ["pending", "ready", "quarantined", "failed"] as const) {
      expect(processingPresentation(state).label).toBeTruthy();
    }
  });
});

describe("formatBytes", () => {
  it("scales the unit to the size", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(3_500_000)).toBe("3.3 MB");
  });
});
