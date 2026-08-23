import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { QuickCreateMenu } from "@/components/QuickCreateMenu";
import type { QuickCreate, QuickCreateAction } from "@/types";

vi.mock("@inertiajs/react", () => ({
  Link: ({
    href,
    children,
    onClick,
    ...rest
  }: {
    href: string;
    children: ReactNode;
    onClick?: () => void;
  }) => (
    <a href={href} onClick={onClick} {...rest}>
      {children}
    </a>
  ),
}));

function action(overrides: Partial<QuickCreateAction> = {}): QuickCreateAction {
  return {
    key: "new-announcement",
    label: "New announcement",
    description: "Draft a notice for your offices.",
    group: "Administration",
    icon: "megaphone",
    href: "/operations/announcements/new",
    external: false,
    ...overrides,
  };
}

function payload(overrides: Partial<QuickCreate> = {}): QuickCreate {
  return {
    actions: [action()],
    scope: { level: "office", label: "Fairfax VA" },
    searchable: false,
    ...overrides,
  };
}

async function openMenu() {
  await userEvent.click(screen.getByRole("button", { name: "Create new" }));
  return screen.findByRole("dialog");
}

describe("QuickCreateMenu", () => {
  it("opens from the header button and lists what the server offered", async () => {
    render(<QuickCreateMenu quickCreate={payload()} />);

    const dialog = await openMenu();

    expect(
      within(dialog).getByRole("link", { name: /New announcement/ }),
    ).toHaveAttribute("href", "/operations/announcements/new");
  });

  it("says which offices the actions apply to", async () => {
    render(<QuickCreateMenu quickCreate={payload()} />);

    const dialog = await openMenu();

    expect(within(dialog).getByText(/Acting for Fairfax VA/)).toBeInTheDocument();
  });

  it("renders only the actions in the payload — it never filters by permission", async () => {
    // Availability was decided server-side; anything absent is absent because
    // it was never serialized, not because this component hid it.
    render(<QuickCreateMenu quickCreate={payload()} />);

    const dialog = await openMenu();

    expect(within(dialog).getAllByRole("link")).toHaveLength(1);
  });

  it("groups actions under their section heading", async () => {
    render(
      <QuickCreateMenu
        quickCreate={payload({
          actions: [
            action({
              key: "new-transaction",
              label: "New transaction",
              group: "Agent",
            }),
            action(),
          ],
        })}
      />,
    );

    const dialog = await openMenu();

    expect(within(dialog).getByRole("heading", { name: "Agent" })).toBeVisible();
    expect(
      within(dialog).getByRole("heading", { name: "Administration" }),
    ).toBeVisible();
  });

  it("discloses an action that leaves the hub", async () => {
    render(
      <QuickCreateMenu
        quickCreate={payload({ actions: [action({ external: true })] })}
      />,
    );

    const dialog = await openMenu();

    expect(
      within(dialog).getByRole("link", { name: /leaves the hub/ }),
    ).toBeInTheDocument();
  });

  it("offers a search box only when the server says the set is large", async () => {
    const { rerender } = render(<QuickCreateMenu quickCreate={payload()} />);
    let dialog = await openMenu();
    expect(within(dialog).queryByLabelText("Search actions")).not.toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    rerender(<QuickCreateMenu quickCreate={payload({ searchable: true })} />);
    dialog = await openMenu();

    expect(within(dialog).getByLabelText("Search actions")).toBeInTheDocument();
  });

  it("focuses the search box on open when there is one", async () => {
    render(<QuickCreateMenu quickCreate={payload({ searchable: true })} />);

    const dialog = await openMenu();

    expect(within(dialog).getByLabelText("Search actions")).toHaveFocus();
  });

  it("narrows the list as the reader types, and explains an empty result", async () => {
    render(
      <QuickCreateMenu
        quickCreate={payload({
          searchable: true,
          actions: [
            action(),
            action({
              key: "new-user",
              label: "New user",
              description: "Invite somebody.",
            }),
          ],
        })}
      />,
    );
    const dialog = await openMenu();

    await userEvent.type(within(dialog).getByLabelText("Search actions"), "user");
    expect(within(dialog).getAllByRole("link")).toHaveLength(1);

    await userEvent.clear(within(dialog).getByLabelText("Search actions"));
    await userEvent.type(within(dialog).getByLabelText("Search actions"), "zzzz");
    expect(within(dialog).getByText(/No actions match/)).toBeInTheDocument();
  });

  it("teaches the next step when the actor has no actions at all", async () => {
    render(<QuickCreateMenu quickCreate={payload({ actions: [] })} />);

    const dialog = await openMenu();

    expect(within(dialog).getByText("Nothing to create yet")).toBeInTheDocument();
    expect(within(dialog).queryByRole("link")).not.toBeInTheDocument();
  });

  it("still renders a usable trigger when the prop is missing entirely", async () => {
    render(<QuickCreateMenu />);

    const dialog = await openMenu();

    expect(within(dialog).getByText("Nothing to create yet")).toBeInTheDocument();
  });

  it("closes on Escape and returns focus to the trigger", async () => {
    render(<QuickCreateMenu quickCreate={payload()} />);
    await openMenu();

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    // Radix restores focus after the close transition, so this settles rather
    // than asserting on the same tick.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Create new" })).toHaveFocus(),
    );
  });

  it("is reachable and operable from the keyboard alone", async () => {
    render(<QuickCreateMenu quickCreate={payload()} />);
    const trigger = screen.getByRole("button", { name: "Create new" });
    trigger.focus();

    await userEvent.keyboard("{Enter}");

    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByRole("link", { name: /New announcement/ }),
    ).toBeVisible();
  });

  it("marks the trigger as opening a dialog", () => {
    render(<QuickCreateMenu quickCreate={payload()} />);

    const trigger = screen.getByRole("button", { name: "Create new" });
    expect(trigger).toHaveAttribute("aria-haspopup", "dialog");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("has no accessibility violations when open", async () => {
    const { baseElement } = render(<QuickCreateMenu quickCreate={payload()} />);
    await openMenu();

    expect(await axe(baseElement)).toHaveNoViolations();
  });
});
