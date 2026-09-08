import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { humanizeMergeKey, MergeValuePreview } from "./MergeValuePreview";

describe("humanizeMergeKey", () => {
  it("reads known keys the way the business says them", () => {
    expect(humanizeMergeKey("agent_split_percent")).toBe("Agent split");
    expect(humanizeMergeKey("annual_cap_amount")).toBe("Annual cap");
  });

  it("falls back to unpicking the underscores", () => {
    expect(humanizeMergeKey("broker_signature_block")).toBe("Broker signature block");
    expect(humanizeMergeKey("brokerSignature")).toBe("Broker signature");
  });

  it("returns an unusable key unchanged rather than blank", () => {
    expect(humanizeMergeKey("__")).toBe("__");
  });
});

describe("MergeValuePreview", () => {
  it("labels each row in words and keeps the merge key underneath", () => {
    render(<MergeValuePreview values={{ agent_split_percent: "70.000" }} />);

    expect(screen.getByText("Agent split")).toBeVisible();
    // Template authors map merge sources by the raw key, so it stays visible —
    // ranked below the human label rather than standing in for it.
    expect(screen.getByText("agent_split_percent")).toBeVisible();
    expect(screen.getByText("70.000")).toBeVisible();
  });

  it("warns about values that would render blank in the agreement", () => {
    render(
      <MergeValuePreview
        values={{ agent_split_percent: "70.000", mentor_percent: "", office_name: " " }}
      />,
    );

    expect(screen.getByText(/2 fields will render blank/i)).toBeVisible();
    expect(screen.getAllByText("Empty")).toHaveLength(2);
  });

  it("says nothing about blanks when every value is filled", () => {
    render(<MergeValuePreview values={{ office_name: "Fairfax" }} />);

    expect(screen.queryByText(/render blank/i)).toBeNull();
    expect(screen.queryByText("Empty")).toBeNull();
  });

  it("orders rows by the label a reader sees, not the raw key", () => {
    render(
      <MergeValuePreview
        values={{ office_split_percent: "30", agent_split_percent: "70" }}
      />,
    );

    const terms = screen.getAllByRole("term");
    expect(within(terms[0]).getByText("Agent split")).toBeVisible();
    expect(within(terms[1]).getByText("Office split")).toBeVisible();
  });

  it("says so when a template declares no merge fields", () => {
    render(<MergeValuePreview values={{}} />);

    expect(screen.getByText(/declares no merge fields/i)).toBeVisible();
  });
});
