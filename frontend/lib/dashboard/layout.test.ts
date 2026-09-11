import { describe, expect, it } from "vitest";

import {
  DASHBOARD_COLUMNS,
  naturalSpan,
  packRows,
  spanClass,
} from "@/lib/dashboard/layout";
import { DASHBOARD_PROFILES } from "@/lib/dashboard/profiles";
import {
  type DashboardWidgetDefinition,
  getDashboardWidget,
} from "@/lib/dashboard/widget-registry";

const identity = (span: number) => span;

function rowTotals(spans: number[]): number[] {
  const packed = packRows(spans, identity);
  const totals: number[] = [];
  for (const entry of packed) {
    totals[entry.row] = (totals[entry.row] ?? 0) + entry.span;
  }
  return totals;
}

describe("packRows", () => {
  it("closes every row on the twelfth column", () => {
    for (const spans of [
      [12],
      [8, 4],
      [8],
      [4],
      [8, 8],
      [8, 4, 4],
      [4, 4, 4, 4],
      [8, 8, 4, 4, 12, 4],
      [4, 8, 4, 4],
    ]) {
      const totals = rowTotals(spans);
      expect(totals.length).toBeGreaterThan(0);
      for (const total of totals) {
        expect(total).toBe(DASHBOARD_COLUMNS);
      }
    }
  });

  it("widens a lone trailing widget into a full-width band", () => {
    // The failure this layout exists to prevent: one four-twelfths panel with
    // eight twelfths of blank canvas beside it, at the bottom of the page.
    expect(packRows([8, 4, 4], identity).map((entry) => entry.span)).toEqual([
      8, 4, 12,
    ]);
  });

  it("splits a short row evenly rather than leaving the hole on one side", () => {
    expect(packRows([8, 4, 4, 4], identity).map((entry) => entry.span)).toEqual([
      8, 4, 6, 6,
    ]);
  });

  it("places each widget in the earliest row it fits, as dense flow would", () => {
    // The narrow widget belongs to a later row by source order, but the row
    // above has exactly its width free.
    const packed = packRows([8, 8, 4], identity);
    expect(packed.map((entry) => entry.row)).toEqual([0, 1, 0]);
    expect(packed.map((entry) => entry.span)).toEqual([8, 12, 4]);
  });

  it("preserves source order, which is the reviewed reading order", () => {
    const packed = packRows(["a", "b", "c"], (item) => (item === "b" ? 4 : 8));
    expect(packed.map((entry) => entry.item)).toEqual(["a", "b", "c"]);
  });

  it("never emits a span outside the grid", () => {
    const packed = packRows([0, 99, 5], identity);
    for (const entry of packed) {
      expect(entry.span).toBeGreaterThanOrEqual(1);
      expect(entry.span).toBeLessThanOrEqual(DASHBOARD_COLUMNS);
    }
  });

  it("handles an empty dashboard", () => {
    expect(packRows([], identity)).toEqual([]);
  });
});

describe("naturalSpan", () => {
  it("gives a rail widget a narrow default and a main widget a reading width", () => {
    const rail = getDashboardWidget("myDay") as DashboardWidgetDefinition;
    const main = getDashboardWidget("training") as DashboardWidgetDefinition;
    const band = getDashboardWidget("performance") as DashboardWidgetDefinition;

    expect(naturalSpan(rail)).toBe(4);
    expect(naturalSpan(main)).toBe(8);
    expect(naturalSpan(band)).toBe(DASHBOARD_COLUMNS);
  });

  it("honors an explicit span from the registry", () => {
    const news = getDashboardWidget("announcements") as DashboardWidgetDefinition;
    expect(naturalSpan(news)).toBe(news.span);
  });
});

describe("every catalogued profile", () => {
  it.each(DASHBOARD_PROFILES.map((profile) => [profile.id, profile] as const))(
    "%s ends on a flush row",
    (_id, profile) => {
      const definitions = profile.widgets
        .map((widget) => getDashboardWidget(widget))
        .filter((definition): definition is DashboardWidgetDefinition =>
          Boolean(definition),
        );
      const packed = packRows(definitions, naturalSpan);
      const totals: number[] = [];
      for (const entry of packed) {
        totals[entry.row] = (totals[entry.row] ?? 0) + entry.span;
      }
      for (const total of totals) {
        expect(total).toBe(DASHBOARD_COLUMNS);
      }
    },
  );
});

describe("spanClass", () => {
  it("emits a literal Tailwind class for every span the packer can produce", () => {
    for (let span = 1; span <= DASHBOARD_COLUMNS; span += 1) {
      expect(spanClass(span)).toBe(`xl:col-span-${span}`);
    }
  });

  it("falls back to the full band for a span outside the grid", () => {
    expect(spanClass(0)).toBe("xl:col-span-12");
    expect(spanClass(99)).toBe("xl:col-span-12");
  });
});
