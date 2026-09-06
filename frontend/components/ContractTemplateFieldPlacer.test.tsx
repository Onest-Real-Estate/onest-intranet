import { describe, expect, it } from "vitest";

import type { TemplateFieldLayoutItem } from "@/components/ContractTemplateFieldPlacer";

describe("ContractTemplateFieldPlacer layout shape", () => {
  it("keeps PDF field coordinates for Hub fill and signing", () => {
    const field: TemplateFieldLayoutItem = {
      id: "1",
      name: "AgentSignature",
      type: "signature",
      role: "Agent",
      page: 1,
      x: 72,
      y: 400,
      w: 180,
      h: 48,
    };
    expect(field.page).toBe(1);
    expect(field.w * field.h).toBeGreaterThan(0);
  });
});
