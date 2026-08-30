import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  FilterControls,
  FilterField,
} from "@/components/design-system/filter-controls";

function fields() {
  return (
    <FilterField label="Office" hideLabel>
      <select aria-label="Office">
        <option>Any office</option>
      </select>
    </FilterField>
  );
}

/**
 * The fields are in the DOM either way; `hidden` is what collapses them. The
 * panel is the only element between the control and the section carrying an
 * id — it is what the toggle's `aria-controls` points at.
 */
function panel(): HTMLElement {
  const region = screen.getByLabelText("Office").closest("div[id]");
  if (!region) throw new Error("no filter panel");
  return region as HTMLElement;
}

describe("FilterControls", () => {
  it("starts closed so an untouched list is a search box and a button", () => {
    render(<FilterControls>{fields()}</FilterControls>);

    expect(panel()).toHaveClass("hidden");
    expect(screen.getByRole("button", { name: /filters/i })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("starts open when something is already narrowing the list", () => {
    // Otherwise a reader arriving on a filtered URL sees a short list with no
    // visible reason for it, and blames the data rather than the filter.
    render(<FilterControls activeCount={2}>{fields()}</FilterControls>);

    expect(panel()).not.toHaveClass("hidden");
  });

  it("keeps the count and the reset reachable while collapsed", () => {
    render(
      <FilterControls activeCount={3} onReset={() => {}}>
        {fields()}
      </FilterControls>,
    );

    expect(screen.getByRole("button", { name: /reset/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /filters/i })).toHaveTextContent("3");
  });

  it("opens on click", async () => {
    const user = userEvent.setup();
    render(<FilterControls>{fields()}</FilterControls>);

    await user.click(screen.getByRole("button", { name: /filters/i }));

    expect(panel()).not.toHaveClass("hidden");
  });

  it("has no toggle at all when the fields are the page's primary control", () => {
    render(<FilterControls collapsible={false}>{fields()}</FilterControls>);

    expect(screen.queryByRole("button", { name: /filters/i })).toBeNull();
    expect(panel()).not.toHaveClass("hidden");
  });
});
