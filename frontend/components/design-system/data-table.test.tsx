import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { DataTable, type DataTableColumn } from "@/components/design-system/data-table";

/**
 * The layout switch reads the table's own measured width, which jsdom reports
 * as 0. Stub the measurement so both sides of the switch are exercised — a
 * ResizeObserver never fires here, and the component measures once on mount
 * anyway.
 */
function measureWidthAs(width: number) {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    width,
    height: 0,
    top: 0,
    left: 0,
    right: width,
    bottom: 0,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect);
}

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

interface WideRow {
  id: string;
  name: string;
  office: string;
}

const wideRows: WideRow[] = [
  { id: "one", name: "Avery Johnson", office: "Fairfax VA" },
];
const wideColumns: DataTableColumn<WideRow>[] = [
  { id: "name", header: "Person", cell: (row) => row.name },
  { id: "office", header: "Office", cell: (row) => row.office, hideBelow: "4xl" },
  {
    id: "actions",
    header: "Actions",
    cell: () => <button type="button">Open</button>,
  },
];

describe("DataTable responsive layout", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps the table and drops narrow-panel columns when the box is wide", () => {
    measureWidthAs(1200);
    render(
      <DataTable
        rows={wideRows}
        columns={wideColumns}
        rowKey={(row) => row.id}
        caption="People"
      />,
    );
    expect(screen.getByRole("table")).toBeInTheDocument();
    // The column still renders; the container query decides whether it shows.
    expect(screen.getByRole("columnheader", { name: /office/i })).toHaveClass(
      "@4xl:table-cell",
    );
  });

  it("becomes cards below the table threshold and keeps every column", () => {
    measureWidthAs(390);
    render(
      <DataTable
        rows={wideRows}
        columns={wideColumns}
        rowKey={(row) => row.id}
        caption="People"
      />,
    );
    expect(screen.queryByRole("table")).toBeNull();
    const list = screen.getByRole("list", { name: "People" });
    expect(list.children).toHaveLength(1);
    // The column the wide table would drop is present, labelled, in the card.
    expect(screen.getByText("Office")).toBeInTheDocument();
    expect(screen.getByText("Fairfax VA")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open" })).toBeInTheDocument();
  });

  it("gives each card a heading so records are navigable by heading", () => {
    measureWidthAs(390);
    render(
      <DataTable
        rows={wideRows}
        columns={wideColumns}
        rowKey={(row) => row.id}
        getRowLabel={(row) => row.name}
        caption="People"
      />,
    );
    // A real heading element, not a role on a div: a heading may only hold
    // phrasing content, which is why it carries the label and not the cell.
    const heading = screen.getByRole("heading", { name: "Avery Johnson", level: 3 });
    expect(heading.tagName).toBe("H3");
  });

  it("treats an unmeasured box as wide rather than as extremely narrow", () => {
    // jsdom reports 0 for every box; a headless render must not collapse to
    // cards just because layout never ran.
    render(
      <DataTable
        rows={wideRows}
        columns={wideColumns}
        rowKey={(row) => row.id}
        caption="People"
      />,
    );
    expect(screen.getByRole("table")).toBeInTheDocument();
  });
});

describe("DataTable horizontal overflow", () => {
  afterEach(() => vi.restoreAllMocks());

  function measureScrollAs(scrollWidth: number, clientWidth: number) {
    for (const [prop, value] of [
      ["scrollWidth", scrollWidth],
      ["clientWidth", clientWidth],
    ] as const) {
      vi.spyOn(HTMLElement.prototype, prop, "get").mockReturnValue(value);
    }
  }

  it("makes a scrolling table reachable from the keyboard", () => {
    measureWidthAs(1200);
    measureScrollAs(1400, 900);
    render(
      <DataTable
        rows={wideRows}
        columns={wideColumns}
        rowKey={(row) => row.id}
        caption="People"
      />,
    );
    // A named <section> is the region: the role is implicit, not an attribute.
    const box = screen.getByRole("region", { name: "Table, scrolls horizontally" });
    expect(box).toHaveAttribute("tabindex", "0");
    expect(box).toHaveAttribute("data-slot", "table-container");
  });

  it("adds no tab stop when the table fits", () => {
    measureWidthAs(1200);
    measureScrollAs(900, 900);
    const { container } = render(
      <DataTable
        rows={wideRows}
        columns={wideColumns}
        rowKey={(row) => row.id}
        caption="People"
      />,
    );
    const box = container.querySelector('[data-slot="table-container"]');
    expect(box).not.toHaveAttribute("tabindex");
    expect(screen.queryByRole("region")).toBeNull();
  });
});
