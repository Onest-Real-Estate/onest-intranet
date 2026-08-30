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

  it("selects every state with Select all", async () => {
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
    await user.click(screen.getByRole("button", { name: /select all/i }));

    const hidden = screen
      .getAllByDisplayValue(/^(MD|VA|CA)$/)
      .filter((node) => node.getAttribute("name") === "jurisdiction_state_codes");
    expect(hidden.map((node) => (node as HTMLInputElement).value).sort()).toEqual([
      "CA",
      "MD",
      "VA",
    ]);
    expect(screen.queryByRole("button", { name: /select all/i })).toBeNull();
  });

  it("Select shown only adds the filtered matches", async () => {
    const user = userEvent.setup();
    render(
      <form>
        <StateMultiSelect
          name="jurisdiction_state_codes"
          label="Jurisdiction states"
          options={options}
          defaultValue={["CA"]}
        />
      </form>,
    );

    await user.click(screen.getByRole("combobox"));
    await user.type(screen.getByRole("textbox", { name: /search states/i }), "m");
    await user.click(screen.getByRole("button", { name: /select shown/i }));

    const hidden = screen
      .getAllByDisplayValue(/^(MD|CA)$/)
      .filter((node) => node.getAttribute("name") === "jurisdiction_state_codes");
    expect(hidden.map((node) => (node as HTMLInputElement).value).sort()).toEqual([
      "CA",
      "MD",
    ]);
  });
});
