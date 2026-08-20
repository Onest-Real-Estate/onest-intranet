import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { DateField } from "@/components/design-system/date-field";

describe("DateField nested dropdowns", () => {
  it("opens month select inside the date popover", async () => {
    const user = userEvent.setup();
    render(
      <DateField
        name="license_expires_on"
        label="License expiration"
        defaultValue="2030-06-30"
        optional
      />,
    );

    await user.click(screen.getByLabelText(/^License expiration/));
    await user.click(screen.getByRole("combobox", { name: "Choose the Month" }));

    const listbox = screen.getByRole("listbox");
    expect(within(listbox).getByRole("option", { name: "Jun" })).toBeVisible();
  });
});
