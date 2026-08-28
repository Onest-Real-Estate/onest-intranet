import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { SearchControl } from "@/components/design-system/search-control";

describe("SearchControl", () => {
  it("supports uncontrolled input, submit, and clear", async () => {
    const user = userEvent.setup();
    const onSearch = vi.fn();
    const onClear = vi.fn();
    render(
      <SearchControl label="Search contracts" onSearch={onSearch} onClear={onClear} />,
    );

    const input = screen.getByRole("searchbox", { name: "Search contracts" });
    await user.type(input, "  client  ");
    fireEvent.submit(input.closest("form") as HTMLFormElement);
    expect(onSearch).toHaveBeenCalledWith("client");

    await user.click(screen.getByRole("button", { name: "Clear search contracts" }));
    expect(input).toHaveValue("");
    expect(onClear).toHaveBeenCalledOnce();
  });

  it("keeps the same accessible control across tones and sizes", () => {
    render(
      <SearchControl label="Search across ONEST" tone="subtle" size="sm" disabled />,
    );
    const input = screen.getByRole("searchbox", { name: "Search across ONEST" });
    expect(input).toBeDisabled();
    // `sm` is one step under the 36px default control height.
    expect(input.className).toContain("h-8");
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(
      <SearchControl label="Search contracts" error="Search is unavailable." />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
