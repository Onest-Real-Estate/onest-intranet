import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/design-system/dialog";
import { Button } from "@/components/ui/button";

function ExampleDialog() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button>Open details</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>Contract details</DialogTitle>
        <DialogDescription>Review the agreement before sharing.</DialogDescription>
        <Button>Continue</Button>
      </DialogContent>
    </Dialog>
  );
}

describe("Dialog", () => {
  it("opens, closes with Escape, and restores focus", async () => {
    const user = userEvent.setup();
    render(<ExampleDialog />);
    const trigger = screen.getByRole("button", { name: "Open details" });
    await user.click(trigger);
    expect(screen.getByRole("dialog")).toBeVisible();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("has no automated accessibility violations", async () => {
    const user = userEvent.setup();
    render(<ExampleDialog />);
    await user.click(screen.getByRole("button", { name: "Open details" }));
    expect(await axe(document.body)).toHaveNoViolations();
  });
});
