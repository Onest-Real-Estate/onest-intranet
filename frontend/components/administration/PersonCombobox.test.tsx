import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PersonCombobox, type PersonOption } from "./PersonCombobox";

const ENDPOINT = "/operations/agent-contracts/recipients";

const PEOPLE: PersonOption[] = [
  {
    id: 9,
    name: "Samuel Reyes",
    email: "samuel@example.com",
    officeId: 1,
    officeName: "Fairfax",
    officeState: "VA",
    licenseState: "VA",
    agentIdentifier: "A1",
  },
  {
    id: 12,
    name: "Sandra Okafor",
    email: "sandra@example.com",
    officeId: 2,
    officeName: "Harrisburg",
    officeState: "PA",
    licenseState: "PA",
    agentIdentifier: "A2",
  },
];

function Harness({ initial = null }: { initial?: PersonOption | null }) {
  const [value, setValue] = useState<PersonOption | null>(initial);
  return (
    <form>
      <PersonCombobox
        id="agent"
        name="recipient_id"
        label="Agent"
        endpoint={ENDPOINT}
        value={value}
        onChange={setValue}
      />
    </form>
  );
}

function hidden(): HTMLInputElement {
  return document.querySelector('input[name="recipient_id"]') as HTMLInputElement;
}

function respondWith(results: PersonOption[]) {
  return vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ results }),
  });
}

describe("PersonCombobox", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", respondWith(PEOPLE));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("exposes a real listbox rather than a div of buttons", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const input = screen.getByLabelText("Agent");
    expect(input).toHaveAttribute("role", "combobox");

    await user.type(input, "sa");
    const list = await screen.findByRole("listbox");
    expect(input).toHaveAttribute("aria-controls", list.id);
    expect(screen.getAllByRole("option")).toHaveLength(2);
  });

  it("moves a highlight with the arrow keys without moving focus", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByLabelText("Agent");

    await user.type(input, "sa");
    await screen.findByRole("listbox");

    const [first, second] = screen.getAllByRole("option");
    expect(first).toHaveAttribute("aria-selected", "true");
    expect(input).toHaveAttribute("aria-activedescendant", first.id);

    await user.keyboard("{ArrowDown}");
    expect(second).toHaveAttribute("aria-selected", "true");
    expect(input).toHaveAttribute("aria-activedescendant", second.id);
    // The caret never left the field, which is what lets typing continue.
    expect(input).toHaveFocus();

    // Wrapping keeps the list reachable in one direction.
    await user.keyboard("{ArrowDown}");
    expect(first).toHaveAttribute("aria-selected", "true");
  });

  it("selects the highlighted person with Enter", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(screen.getByLabelText("Agent"), "sa");
    await screen.findByRole("listbox");
    await user.keyboard("{ArrowDown}{Enter}");

    expect(hidden().value).toBe("12");
    expect(screen.getByText("Sandra Okafor")).toBeVisible();
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("jumps to the ends with Home and End", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(screen.getByLabelText("Agent"), "sa");
    await screen.findByRole("listbox");
    await user.keyboard("{End}");

    expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{Home}");
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "true");
  });

  it("closes on Escape without choosing anyone", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(screen.getByLabelText("Agent"), "sa");
    await screen.findByRole("listbox");
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("listbox")).toBeNull();
    expect(hidden().value).toBe("");
  });

  it("selects on click and posts the id", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(screen.getByLabelText("Agent"), "sa");
    await screen.findByRole("listbox");
    await user.click(screen.getByRole("option", { name: /samuel reyes/i }));

    expect(hidden().value).toBe("9");
  });

  it("shows the chosen person as a record and lets them be changed", async () => {
    const user = userEvent.setup();
    render(<Harness initial={PEOPLE[0]} />);

    expect(screen.getByText("Samuel Reyes")).toBeVisible();
    expect(screen.getByText(/samuel@example\.com · Fairfax · VA/)).toBeVisible();
    expect(hidden().value).toBe("9");

    await user.click(screen.getByRole("button", { name: /clear samuel reyes/i }));

    expect(hidden().value).toBe("");
    expect(screen.getByLabelText("Agent")).toBeVisible();
  });

  it("waits for a usable query before searching", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(screen.getByLabelText("Agent"), "s");

    // The hint renders both visibly and in the polite live region.
    await waitFor(() =>
      expect(screen.getAllByText(/type at least 2 characters/i).length).toBe(2),
    );
    expect(fetch).not.toHaveBeenCalled();
  });

  it("says when nobody matches", async () => {
    vi.stubGlobal("fetch", respondWith([]));
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(screen.getByLabelText("Agent"), "zz");

    expect(await screen.findByText(/nobody in your scope matches/i)).toBeVisible();
  });

  it("reports a failed search instead of showing an empty list", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(screen.getByLabelText("Agent"), "sa");

    expect(await screen.findByText(/search could not run/i)).toBeVisible();
  });

  it("portals the listbox outside overflow-hidden ancestors", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <div className="overflow-hidden" style={{ height: 48 }}>
        <Harness />
      </div>,
    );

    await user.type(screen.getByLabelText("Agent"), "sa");
    const list = await screen.findByRole("listbox");
    const clipped = container.querySelector(".overflow-hidden");

    expect(clipped).not.toBeNull();
    expect(clipped?.contains(list)).toBe(false);
    expect(list.closest('[data-slot="popover-content"]')).not.toBeNull();
  });

  it("appends q with & when the endpoint already has a query string", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ results: PEOPLE }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(
      <form>
        <PersonCombobox
          id="agent"
          name="recipient_id"
          label="Agent"
          endpoint="/transactions/people?role=agent&officeKey=fairfax-va"
          value={null}
          onChange={() => {}}
        />
      </form>,
    );

    await user.type(screen.getByLabelText("Agent"), "sa");
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const calledUrl = String(fetchMock.mock.calls[0]?.[0] ?? "");
    expect(calledUrl).toContain("role=agent");
    expect(calledUrl).toContain("officeKey=fairfax-va");
    expect(calledUrl).toMatch(/[?&]q=sa/);
    expect(calledUrl).not.toContain("?q=");
  });
});
