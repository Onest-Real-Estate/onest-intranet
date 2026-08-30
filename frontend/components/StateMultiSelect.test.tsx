import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { StateMultiSelect } from "@/components/StateMultiSelect";

const options = [
  { code: "MD", name: "Maryland" },
  { code: "VA", name: "Virginia" },
  { code: "CA", name: "California" },
];

describe("StateMultiSelect", () => {
  it("submits selected state codes as repeated hidden inputs", async () => {
    const user = userEvent.setup();
    render(
      <form>
        <StateMultiSelect
          name="jurisdiction_state_codes"
          label="Jurisdiction states"
          options={options}
        />
      </form>,
    );

    await user.click(screen.getByRole("combobox"));
    await user.click(screen.getByLabelText(/VA/i));
    await user.click(screen.getByLabelText(/MD/i));

    const hidden = screen
      .getAllByDisplayValue(/^(VA|MD)$/)
      .filter((node) => node.getAttribute("name") === "jurisdiction_state_codes");
    expect(hidden.map((node) => (node as HTMLInputElement).value).sort()).toEqual([
      "MD",
      "VA",
    ]);
  });

  it("filters states by typed search", async () => {
    const user = userEvent.setup();
    render(
      <StateMultiSelect
        name="jurisdiction_state_codes"
        label="Jurisdiction states"
        options={options}
      />,
    );

    await user.click(screen.getByRole("combobox"));
    const search = screen.getByRole("textbox", { name: /search states/i });
    await user.type(search, "virg");

    expect(screen.getByLabelText(/VA/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/MD/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/CA/i)).not.toBeInTheDocument();
  });
});
