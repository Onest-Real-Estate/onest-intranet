import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

vi.mock("@inertiajs/react", () => ({
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

import { Announcements } from "@/components/dashboard/Announcements";
import type { DashboardAnnouncements } from "@/types";

const data: DashboardAnnouncements = {
  featured: {
    id: 1,
    href: "/announcements/1",
    tag: "Policy",
    title: "Updated commission schedule takes effect 1 September",
    excerpt: "Splits and cap thresholds change for the new plan year.",
    imageUrl: "/static/news/commission.jpg",
  },
  items: [
    {
      id: 2,
      href: "/announcements/2",
      tag: "Event",
      title: "Fall kickoff",
      excerpt: "Doors at 9.",
    },
    {
      id: 3,
      href: "/announcements/3",
      tag: "Training",
      title: "New contract forms",
      excerpt: "A walkthrough.",
      imageUrl: "/static/news/forms.jpg",
    },
  ],
};

function track(): HTMLElement {
  const element = screen.getByRole("region", {
    name: "News and announcements",
  }).firstElementChild;
  if (!(element instanceof HTMLElement)) {
    throw new Error("the carousel has no track");
  }
  return element;
}

describe("Announcements", () => {
  it("shows one story at a time, featured first", () => {
    render(<Announcements data={data} />);

    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(screen.getByRole("article")).toHaveAccessibleName(
      /^1 of 3: Updated commission schedule/,
    );
    expect(screen.getByText("1 / 3")).toBeVisible();
    expect(track()).toHaveStyle({ transform: "translateX(-0%)" });
  });

  it("renders artwork decoratively and holds the frame without it", () => {
    const { container } = render(<Announcements data={data} />);

    const images = container.querySelectorAll("img");
    expect(images).toHaveLength(2);
    // The headline over it names the story; a duplicate alt reads twice.
    expect(images[0]).toHaveAttribute("alt", "");
    // The story with no artwork still gets a frame, so the band keeps its
    // height as you move through them.
    expect(container.querySelectorAll(".h-56")).toHaveLength(3);
  });

  it("moves the track exactly one story at a time", async () => {
    render(<Announcements data={data} />);

    expect(
      screen.getByRole("button", { name: "Previous announcement" }),
    ).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Next announcement" }));

    expect(track()).toHaveStyle({ transform: "translateX(-100%)" });
    expect(screen.getByText("2 / 3")).toBeVisible();
    expect(screen.getByRole("button", { name: "Previous announcement" })).toBeEnabled();
  });

  it("stops at the last story", async () => {
    render(<Announcements data={data} />);

    const next = screen.getByRole("button", { name: "Next announcement" });
    await userEvent.click(next);
    await userEvent.click(next);

    expect(track()).toHaveStyle({ transform: "translateX(-200%)" });
    expect(next).toBeDisabled();
  });

  it("jumps straight to a story from its marker", async () => {
    render(<Announcements data={data} />);

    const markers = screen.getAllByRole("button", { name: /^Show announcement/ });
    expect(markers[0]).toHaveAttribute("aria-current", "true");

    await userEvent.click(markers[2]);

    expect(track()).toHaveStyle({ transform: "translateX(-200%)" });
    expect(markers[2]).toHaveAttribute("aria-current", "true");
  });

  it("keeps the stories that are off-frame out of the reading order", async () => {
    render(<Announcements data={data} />);
    expect(screen.getAllByRole("article")).toHaveLength(1);

    await userEvent.click(screen.getByRole("button", { name: "Next announcement" }));

    expect(screen.getByRole("article")).toHaveAccessibleName(/^2 of 3: Fall kickoff/);
  });

  it("offers no controls for a single story", () => {
    render(<Announcements data={{ featured: data.featured, items: [] }} />);

    expect(screen.queryByRole("button", { name: "Next announcement" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Show announcement/ })).toBeNull();
  });

  it("has no detectable accessibility violations", async () => {
    const { container } = render(<Announcements data={data} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
