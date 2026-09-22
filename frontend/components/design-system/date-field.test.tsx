import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { DateField, DatePicker } from "@/components/design-system/date-field";
import { formatFormDate } from "@/lib/dates";

describe("DateField", () => {
  it("posts an ISO date through a hidden input, not a native date picker", async () => {
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
    expect(await axe(container)).toHaveNoViolations();

    // fireEvent, not userEvent: Radix popover + day-grid pointer checks stall
    // the simulated user under full-suite load past the test timeout.
    fireEvent.click(screen.getByLabelText(/^Start date/));
    fireEvent.click(await screen.findByRole("button", { name: /August 15/ }));

    expect(container.querySelector("input[name='start_date']")).toHaveValue(
      "2026-08-15",
    );
  });

  it("keeps calendar + time controls instead of datetime-local", async () => {
    const onChange = vi.fn();
    const { container } = render(
      <DatePicker
        id="occurs-at"
        aria-label="Occurs at"
        value="2026-09-22T19:02"
        onChange={onChange}
        includeTime
      />,
    );

    expect(container.querySelector("input[type='datetime-local']")).toBeNull();
    expect(screen.getByLabelText("Occurs at")).toHaveTextContent(
      formatFormDate("2026-09-22T19:02", true),
    );

    fireEvent.click(screen.getByLabelText("Occurs at"));
    const timeInput = await screen.findByLabelText("Time");
    expect(timeInput).toHaveAttribute("type", "time");
    expect(timeInput).toHaveValue("19:02");

    fireEvent.click(await screen.findByRole("button", { name: /September 15/ }));
    expect(onChange).toHaveBeenCalled();
    const next = onChange.mock.calls.at(-1)?.[0] as string;
    expect(next).toMatch(/^2026-09-15T\d{2}:\d{2}$/);
  });
});
