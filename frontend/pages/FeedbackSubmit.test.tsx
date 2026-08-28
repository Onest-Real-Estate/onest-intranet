import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import FeedbackSubmit from "@/pages/FeedbackSubmit";
import type { FeedbackSubmitPageProps } from "@/types";

const pageProps = vi.hoisted(() => ({ current: {} as FeedbackSubmitPageProps }));

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/support/feedback" }),
  Link: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
  Head: () => null,
}));

function setPage(overrides: Partial<FeedbackSubmitPageProps> = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "agent@onest.realestate",
      name: "Avery Johnson",
      headshotUrl: null,
      permissions: [],
      roles: ["realtor"],
      roleLabel: "Realtor",
      isStaff: false,
      isSuperuser: false,
    },
    csrfToken: "token",
    requestId: "request-1",
    features: {},
    primaryOffice: null,
    shell: null,
    notifications: null,
    categories: [
      { value: "bug", label: "Something is broken" },
      { value: "general_help", label: "I need help" },
    ],
    urgencies: [
      { value: "blocking", label: "I cannot work until this is fixed" },
      { value: "minor", label: "Minor — whenever you get to it" },
    ],
    disclosure: ["Your name, work email, and office, so support can reply."],
    contacts: [],
    pageUrl: "",
    errors: { fields: {}, form: [] },
    ...overrides,
  } as FeedbackSubmitPageProps;
}

beforeEach(() => {
  setPage();
});

describe("FeedbackSubmit", () => {
  it("offers the category as real radios, not a dropdown", async () => {
    const user = userEvent.setup();
    render(<FeedbackSubmit />);

    const choice = screen.getByRole("radio", { name: /something is broken/i });
    await user.click(choice);
    expect(choice).toBeChecked();
    // One name, so the browser enforces single-select for free.
    expect(choice).toHaveAttribute("name", "category");
  });

  it("groups the choices under a real legend", () => {
    render(<FeedbackSubmit />);
    expect(
      screen.getByRole("group", { name: "What kind of report is this?" }),
    ).toBeVisible();
    expect(
      screen.getByRole("group", { name: "How urgent is this for you?" }),
    ).toBeVisible();
  });

  it("carries the page the reader came from into the submission", () => {
    // `document.referrer` is empty for an Inertia visit, so the server hands
    // this down from the `?from=` the trigger appended.
    setPage({ pageUrl: "/operations/tasks?page=2" });
    const { container } = render(<FeedbackSubmit />);
    expect(container.querySelector('input[name="pageUrl"]')).toHaveValue(
      "/operations/tasks?page=2",
    );
  });

  it("mints one submission key so a double submit lands on one ticket", () => {
    const { container } = render(<FeedbackSubmit />);
    const key = container.querySelector('input[name="submissionKey"]');
    expect(key).not.toBeNull();
    expect((key as HTMLInputElement).value.length).toBeGreaterThan(8);
  });

  it("discloses what is captured, from the server's own list", () => {
    render(<FeedbackSubmit />);
    expect(screen.getByText(/your name, work email, and office/i)).toBeVisible();
  });

  it("posts as a native multipart form so a screenshot needs no second path", () => {
    const { container } = render(<FeedbackSubmit />);
    const form = container.querySelector("form");
    expect(form).toHaveAttribute("method", "post");
    expect(form).toHaveAttribute("enctype", "multipart/form-data");
    expect(form).toHaveAttribute("action", "/support/feedback/send");
  });

  it("lists real office contacts when the office has them", () => {
    setPage({
      contacts: [
        {
          key: "itSupport",
          role: "IT support",
          purpose: "Logins and devices",
          name: "Dana Ruiz",
          email: "it@onest.realestate",
          phone: "(703) 555-0100",
        },
      ],
    });
    render(<FeedbackSubmit />);
    expect(screen.getByText("Dana Ruiz")).toBeVisible();
    expect(screen.getByRole("link", { name: /email/i })).toHaveAttribute(
      "href",
      "mailto:it@onest.realestate",
    );
  });

  it("shows no contact section at all when the office has none", () => {
    // A fabricated contact is worse than none.
    render(<FeedbackSubmit />);
    expect(screen.queryByText("Or talk to somebody")).toBeNull();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<FeedbackSubmit />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
