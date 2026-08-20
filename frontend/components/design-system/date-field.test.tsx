import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";

import { DateField } from "@/components/design-system/date-field";
import { formatFormDate } from "@/lib/dates";

describe("DateField", () => {
  it("posts an ISO date through a hidden input, not a native date picker", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <form>
        <DateField
          name="start_date"
          label="Start date"
          defaultValue="2026-08-20"
          optional
        />
      </form>,
    );

    expect(container.querySelector("input[type='date']")).toBeNull();
    expect(container.querySelector("input[name='start_date']")).toHaveValue(
      "2026-08-20",
    );
    expect(screen.getByLabelText(/^Start date/)).toHaveTextContent(
      formatFormDate("2026-08-20"),
    );

    await user.click(screen.getByLabelText(/^Start date/));
    await user.click(screen.getByRole("button", { name: /August 15/ }));

    expect(container.querySelector("input[name='start_date']")).toHaveValue(
      "2026-08-15",
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
