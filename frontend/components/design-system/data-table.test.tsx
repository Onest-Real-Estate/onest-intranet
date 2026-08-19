import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { DataTable, type DataTableColumn } from "@/components/design-system/data-table";

interface Row {
  id: string;
  name: string;
}

const rows: Row[] = [{ id: "one", name: "Avery Johnson" }];
const columns: DataTableColumn<Row>[] = [
  { id: "name", header: "Client", cell: (row) => row.name, sortable: true },
];

describe("DataTable", () => {
  it("announces sorting and supports selection", async () => {
    const user = userEvent.setup();
    const onSortChange = vi.fn();
    const onSelectionChange = vi.fn();
    render(
      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(row) => row.id}
        caption="Clients"
        sort={{ key: "name", direction: "asc" }}
        onSortChange={onSortChange}
        selectedKeys={new Set()}
        onSelectionChange={onSelectionChange}
        getRowLabel={(row) => row.name}
      />,
    );

    expect(screen.getByRole("columnheader", { name: /client/i })).toHaveAttribute(
      "aria-sort",
      "ascending",
    );
    await user.click(screen.getByRole("button", { name: /client/i }));
    expect(onSortChange).toHaveBeenCalledWith({ key: "name", direction: "desc" });
    await user.click(screen.getByRole("checkbox", { name: "Select Avery Johnson" }));
    expect(onSelectionChange.mock.calls[0][0]).toEqual(new Set(["one"]));
  });

  it("drops its own frame inside a card so borders do not double up", () => {
    const { container } = render(
      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(row) => row.id}
        caption="Clients"
        frame="bare"
      />,
    );
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper.className).not.toContain("border");
  });

  it("renders an empty state rather than an empty grid", () => {
    render(
      <DataTable
        rows={[]}
        columns={columns}
        rowKey={(row) => row.id}
        caption="Clients"
        emptyTitle="No matching clients"
      />,
    );
    expect(screen.getByRole("heading", { name: "No matching clients" })).toBeVisible();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(
      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(row) => row.id}
        caption="Clients"
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
