import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TimezonePicker } from "@/components/design-system/timezone-field";
import { filterIanaTimezones, listIanaTimezones } from "@/lib/timezones";

describe("listIanaTimezones", () => {
  it("puts preferred brokerage zones ahead of the alphabetical remainder", () => {
    const zones = listIanaTimezones();
    expect(zones[0]).toBe("America/New_York");
    expect(zones).toContain("UTC");
    expect(zones).toContain("Asia/Kathmandu");
    expect(zones.indexOf("America/New_York")).toBeLessThan(
      zones.indexOf("Asia/Kathmandu"),
    );
  });
});
describe("filterIanaTimezones", () => {
  const catalog = ["America/New_York", "America/Chicago", "Asia/Kathmandu", "UTC"];

  it("matches city fragments and underscore-insensitive needles", () => {
    expect(filterIanaTimezones(catalog, "kath")).toEqual(["Asia/Kathmandu"]);
    expect(filterIanaTimezones(catalog, "new york")).toEqual(["America/New_York"]);
    expect(filterIanaTimezones(catalog, "")).toEqual(catalog);
  });
});

describe("TimezonePicker", () => {
  it("filters the select list from the search control", () => {
    const zones = ["America/New_York", "America/Chicago", "Asia/Kathmandu", "UTC"];
    render(
      <TimezonePicker
        id="date-tz"
        value="America/New_York"
        onChange={() => {}}
        zones={zones}
      />,
    );

    fireEvent.change(screen.getByLabelText("Search timezones"), {
      target: { value: "kath" },
    });
    fireEvent.click(screen.getByRole("combobox"));

    expect(screen.getByRole("option", { name: "Asia/Kathmandu" })).toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: "America/Chicago" }),
    ).not.toBeInTheDocument();
  });
});
