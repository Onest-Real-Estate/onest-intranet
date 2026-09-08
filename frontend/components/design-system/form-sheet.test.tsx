import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FormSheet, FormSheetBody } from "@/components/design-system/form-sheet";

describe("FormSheet", () => {
  it("renders title, description, body, and footer when open", () => {
    render(
      <FormSheet
        open
        onOpenChange={() => {}}
        title="New resource"
        description="Publish to a branch in your scope."
        footer={<button type="button">Create</button>}
      >
        <FormSheetBody>
          <label htmlFor="demo">Demo</label>
          <input id="demo" />
        </FormSheetBody>
      </FormSheet>,
    );
    expect(screen.getByRole("heading", { name: /new resource/i })).toBeInTheDocument();
    expect(screen.getByText(/publish to a branch in your scope/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Demo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create/i })).toBeInTheDocument();
    // Close affordance is always available.
    expect(screen.getByRole("button", { name: /close/i })).toBeInTheDocument();
  });

  it("does not render content when closed", () => {
    render(
      <FormSheet open={false} onOpenChange={() => {}} title="Hidden">
        <FormSheetBody>content</FormSheetBody>
      </FormSheet>,
    );
    expect(screen.queryByText("content")).not.toBeInTheDocument();
  });

  it("reports close intent through onOpenChange", async () => {
    const onOpenChange = vi.fn();
    const user = userEvent.setup();
    render(
      <FormSheet open onOpenChange={onOpenChange} title="Closable">
        <FormSheetBody>body</FormSheetBody>
      </FormSheet>,
    );
    await user.click(screen.getByRole("button", { name: /close/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
