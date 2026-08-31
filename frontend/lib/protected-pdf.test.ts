import { afterEach, describe, expect, it, vi } from "vitest";

import { loadProtectedPdfBytes } from "@/lib/protected-pdf";

describe("loadProtectedPdfBytes", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads PDF bytes with same-origin credentials", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => "application/pdf" },
      arrayBuffer: async () => new Uint8Array([37, 80, 68, 70]).buffer,
    });
    vi.stubGlobal("fetch", fetchMock);

    const bytes = await loadProtectedPdfBytes(
      "/operations/contract-templates/templates/4/source.pdf",
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/operations/contract-templates/templates/4/source.pdf",
      {
        credentials: "same-origin",
        headers: { Accept: "application/pdf" },
      },
    );
    expect(bytes.byteLength).toBe(4);
  });

  it("surfaces permission failures clearly", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        headers: { get: () => "text/html" },
      }),
    );

    await expect(
      loadProtectedPdfBytes("/operations/contract-templates/templates/4/source.pdf"),
    ).rejects.toThrow(/permission/i);
  });
});
