import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

vi.mock("@inertiajs/react", () => ({
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

import { MyDay } from "@/components/dashboard/MyDay";
import type { AgendaEvent, DashboardSchedule } from "@/types";

function event(overrides: Partial<AgendaEvent> = {}): AgendaEvent {
  return {
    id: "e1",
    dedupeKey: "e1",
    source: "meeting",
    sourceLabel: "Meeting",
    title: "Listing consultation",
    startAt: "2026-03-02T14:00:00+00:00",
    endAt: "2026-03-02T15:00:00+00:00",
    allDay: false,
    localDate: "2026-03-02",
    timeLabel: "2:00 p.m. – 3:00 p.m.",
    dayLabel: "Today",
    isToday: true,
    location: "Fairfax VA",
    status: "confirmed",
    statusLabel: "",
    priority: "normal",
    overdue: false,
    context: "Client · Ramirez",
    ctaLabel: "Open",
    ctaHref: "/operations/tasks/abc",
    ...overrides,
  };
}

function schedule(overrides: Partial<DashboardSchedule> = {}): DashboardSchedule {
  const base: DashboardSchedule = {
    dateLabel: "Monday, March 2",
    timezone: "UTC",
    overdue: [],
    today: [event()],
    upcoming: [],
    total: 1,
    viewAllHref: "/hub/my-reservations",
    viewAllLabel: "View my reservations",
    ...overrides,
  };
  return base;
}

describe("MyDay", () => {
  it("renders each event's time, title, source, and location", () => {
    render(<MyDay schedule={schedule()} />);

    expect(screen.getByText("2:00 p.m. – 3:00 p.m.")).toBeVisible();
    expect(screen.getByText("Listing consultation")).toBeVisible();
    expect(screen.getByText("Meeting")).toBeVisible();
    expect(screen.getByText("Fairfax VA")).toBeVisible();
  });

  it("keeps overdue work above today and upcoming, in that order", () => {
    render(
      <MyDay
        schedule={schedule({
          overdue: [event({ id: "o1", title: "Missed deadline", overdue: true })],
          today: [event({ id: "t1", title: "Today thing" })],
          upcoming: [event({ id: "u1", title: "Tomorrow thing" })],
          total: 3,
        })}
      />,
    );

    const headings = screen.getAllByRole("heading", { level: 3 });
    expect(headings.map((h) => h.textContent)).toEqual([
      "Overdue",
      "Today",
      "Upcoming",
    ]);
  });

  it("names the overdue section in words, not only colour", () => {
    render(
      <MyDay
        schedule={schedule({
          overdue: [event({ id: "o1", overdue: true })],
          today: [],
          total: 1,
        })}
      />,
    );
    // The reader most likely to miss the tint is the one who most needs it.
    expect(screen.getByRole("region", { name: "Overdue" })).toBeVisible();
  });

  it("omits a section that has no events rather than showing an empty heading", () => {
    render(<MyDay schedule={schedule()} />);
    expect(screen.queryByRole("region", { name: "Overdue" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Upcoming" })).toBeNull();
  });

  it("shows an all-day row as all day, never a synthesized midnight", () => {
    render(
      <MyDay
        schedule={schedule({
          today: [event({ allDay: true, timeLabel: "All day", endAt: null })],
        })}
      />,
    );
    expect(screen.getByText("All day")).toBeVisible();
    expect(screen.queryByText(/12:00 a\.m\./)).toBeNull();
  });

  it("says in words when an event is only tentative", () => {
    render(
      <MyDay
        schedule={schedule({
          today: [event({ status: "tentative", statusLabel: "Tentative" })],
        })}
      />,
    );
    expect(screen.getByText("Tentative")).toBeVisible();
  });

  it("adds no status chip for a confirmed event", () => {
    render(<MyDay schedule={schedule()} />);
    expect(screen.queryByText("Confirmed")).toBeNull();
  });

  it("links each row to the record, which re-authorizes on arrival", () => {
    render(<MyDay schedule={schedule()} />);
    const link = screen.getByRole("link", { name: /Listing consultation/ });
    expect(link).toHaveAttribute("href", "/operations/tasks/abc");
  });

  it("renders a row with no destination as plain text, not a dead link", () => {
    render(
      <MyDay
        schedule={schedule({
          today: [event({ ctaHref: "", ctaLabel: "", title: "No link here" })],
        })}
      />,
    );
    expect(screen.getByText("No link here")).toBeVisible();
    expect(screen.queryByRole("link", { name: /No link here/ })).toBeNull();
  });

  it("keeps the rows when a source failed, and says the list is incomplete", () => {
    render(<MyDay schedule={schedule()} partialFailure />);

    // A source being down is a reason to caveat the list, not to hide it.
    expect(screen.getByText("Listing consultation")).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent(/may be incomplete/i);
  });

  it("never names the source that failed", () => {
    const { container } = render(<MyDay schedule={schedule()} partialFailure />);
    expect(container.textContent).not.toMatch(/outlook|microsoft|training/i);
  });

  it("shows how many rows were trimmed when the feed is capped", () => {
    render(<MyDay schedule={schedule({ total: 9 })} truncated />);
    expect(screen.getByText("1 of 9")).toBeVisible();
  });

  it("shows the date when nothing was trimmed", () => {
    render(<MyDay schedule={schedule()} />);
    expect(screen.getByText("Monday, March 2")).toBeVisible();
  });

  it("points the footer at the calendar destination the server chose", () => {
    render(<MyDay schedule={schedule()} />);
    const link = screen.getByRole("link", { name: /View my reservations/ });
    expect(link).toHaveAttribute("href", "/hub/my-reservations");
  });

  it("truncates long titles rather than breaking the column layout", () => {
    render(
      <MyDay
        schedule={schedule({
          today: [
            event({
              title:
                "Quarterly compliance review with the regional brokerage team and outside counsel",
              location:
                "Conference Room B, Second Floor, Fairfax Regional Office, Virginia",
            }),
          ],
        })}
      />,
    );
    const title = screen.getByText(/Quarterly compliance review/);
    // Clamped, not truncated: two lines of a real title beat an ellipsis at
    // thirty characters. `min-w-0` is the part that actually prevents the
    // overflow — without it the flex item sizes to its text and pushes past
    // the card's right edge.
    expect(title.className).toContain("line-clamp-2");
    expect(title.className).toContain("min-w-0");
  });

  it("does not reformat times against the browser clock", () => {
    // The server rendered these in the reader's timezone; a component that
    // re-derived them would let a laptop on the wrong timezone disagree with
    // the buckets the server computed.
    render(
      <MyDay
        schedule={schedule({
          today: [
            event({ timeLabel: "9:15 a.m.", startAt: "2026-03-02T23:59:00+00:00" }),
          ],
        })}
      />,
    );
    expect(screen.getByText("9:15 a.m.")).toBeVisible();
  });

  it("groups rows so each section's events are inside it", () => {
    render(
      <MyDay
        schedule={schedule({
          overdue: [event({ id: "o1", title: "Missed", overdue: true })],
          today: [event({ id: "t1", title: "Later today" })],
          total: 2,
        })}
      />,
    );
    const overdue = screen.getByRole("region", { name: "Overdue" });
    expect(within(overdue).getByText("Missed")).toBeVisible();
    expect(within(overdue).queryByText("Later today")).toBeNull();
  });

  it("names the day on a row that is not today", () => {
    // Two upcoming rows on different days: 6pm tomorrow sitting above 5pm the
    // day after is correct, and reads as a sorting bug without the day.
    render(
      <MyDay
        schedule={schedule({
          today: [],
          upcoming: [
            event({
              id: "u1",
              title: "Tomorrow evening",
              timeLabel: "6:00 p.m.",
              dayLabel: "Tomorrow",
              isToday: false,
            }),
            event({
              id: "u2",
              title: "Day after, earlier",
              timeLabel: "5:00 p.m.",
              dayLabel: "Wed, Mar 4",
              isToday: false,
            }),
          ],
          total: 2,
        })}
      />,
    );

    expect(screen.getByText("Tomorrow")).toBeVisible();
    expect(screen.getByText("Wed, Mar 4")).toBeVisible();
  });

  it("does not repeat the day on today's own rows", () => {
    render(<MyDay schedule={schedule()} />);
    // Once, as the section heading — not again on every row beneath it.
    expect(screen.getAllByText("Today")).toHaveLength(1);
    expect(screen.getByRole("heading", { name: "Today" })).toBeVisible();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(
      <MyDay
        schedule={schedule({
          overdue: [event({ id: "o1", overdue: true })],
          upcoming: [event({ id: "u1", dayLabel: "Tomorrow" })],
          total: 3,
        })}
        partialFailure
        truncated
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
