import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DateField } from "@/components/design-system/date-field";

describe("DateField nested dropdowns", () => {
  it("opens month select inside the date popover", async () => {
    render(
      <DateField
        name="license_expires_on"
        label="License expiration"
        defaultValue="2030-06-30"
        optional
      />,
    );

    fireEvent.click(screen.getByLabelText(/^License expiration/));
    fireEvent.click(await screen.findByRole("combobox", { name: "Choose the Month" }));

    const listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByRole("option", { name: "Jun" })).toBeVisible();
  });
});
