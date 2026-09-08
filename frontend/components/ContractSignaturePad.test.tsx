import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ContractSignaturePad } from "./ContractSignaturePad";

/**
 * jsdom has no canvas implementation, so the 2D context is stubbed. These
 * tests are about the component's behaviour — which mode is active, what it
 * reports upward, whether Clear leaves the field consistent — not about the
 * pixels, which only a browser can produce.
 */
function stubCanvas() {
  const context = {
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 0,
    lineCap: "",
    lineJoin: "",
    font: "",
    setTransform: vi.fn(),
    fillRect: vi.fn(),
    fillText: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    measureText: vi.fn(() => ({ width: 120 })),
  };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    context as unknown as CanvasRenderingContext2D,
  );
  vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue(
    "data:image/png;base64,signed",
  );
  return context;
}

describe("ContractSignaturePad", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    stubCanvas();
  });

  it("tells assistive technology which method is active", async () => {
    const user = userEvent.setup();
    render(<ContractSignaturePad onChange={vi.fn()} />);

    const draw = screen.getByRole("button", { name: "Draw" });
    const type = screen.getByRole("button", { name: "Type" });
    expect(draw).toHaveAttribute("aria-pressed", "true");
    expect(type).toHaveAttribute("aria-pressed", "false");

    await user.click(type);

    expect(type).toHaveAttribute("aria-pressed", "true");
    expect(draw).toHaveAttribute("aria-pressed", "false");
  });

  it("keeps the page's one gold button for the submit below it", () => {
    render(<ContractSignaturePad onChange={vi.fn()} />);

    // The active mode used to be a filled brand-gold button, which competed
    // with "Apply signature and finish" for the page's single primary signal.
    for (const name of ["Draw", "Type"]) {
      expect(screen.getByRole("button", { name }).className).not.toContain(
        "bg-brand-gold",
      );
    }
  });

  it("offers a keyboard path to a signature", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ContractSignaturePad onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "Type" }));
    await user.type(screen.getByLabelText(/type your full legal name/i), "Avery Agent");

    expect(onChange).toHaveBeenLastCalledWith("data:image/png;base64,signed");
  });

  it("clears the typed name along with the canvas", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ContractSignaturePad onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "Type" }));
    const field = screen.getByLabelText(/type your full legal name/i);
    await user.type(field, "Avery");
    expect(field).toHaveValue("Avery");

    await user.click(screen.getByRole("button", { name: /clear/i }));

    // The old Clear wiped the canvas but left the name in the box, so the form
    // showed a signature while reporting itself empty.
    expect(field).toHaveValue("");
    expect(onChange).toHaveBeenLastCalledWith("");
  });

  it("discards the signature when the method changes", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ContractSignaturePad onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "Type" }));
    await user.type(screen.getByLabelText(/type your full legal name/i), "Avery");
    onChange.mockClear();

    await user.click(screen.getByRole("button", { name: "Draw" }));

    expect(onChange).toHaveBeenLastCalledWith("");
    expect(screen.queryByLabelText(/type your full legal name/i)).toBeNull();
  });

  it("renders the backing store at the device pixel ratio", () => {
    vi.stubGlobal("devicePixelRatio", 2);
    const { container } = render(<ContractSignaturePad onChange={vi.fn()} />);

    const canvas = container.querySelector("canvas") as HTMLCanvasElement;
    // jsdom reports clientWidth 0, so height is the checkable half: a 180px
    // pad on a 2x display needs a 360px buffer or the sealed PNG is upscaled.
    expect(canvas.height).toBe(360);
    vi.unstubAllGlobals();
  });

  it("names the pad and its keyboard alternative", () => {
    const { container } = render(<ContractSignaturePad onChange={vi.fn()} />);

    const canvas = container.querySelector("canvas") as HTMLCanvasElement;
    expect(canvas.getAttribute("aria-label")).toMatch(/switch to type/i);
  });
});
