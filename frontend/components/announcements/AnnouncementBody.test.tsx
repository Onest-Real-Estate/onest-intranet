import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";

import { AnnouncementBody } from "@/components/announcements/AnnouncementBody";
import type { AnnouncementBlock } from "@/types";

function paragraph(value: string): AnnouncementBlock {
  return { type: "paragraph", spans: [{ type: "text", value }] };
}

describe("AnnouncementBody", () => {
  it("renders each block type as a real element", () => {
    const { container } = render(
      <AnnouncementBody
        blocks={[
          { type: "heading", level: 2, spans: [{ type: "text", value: "Notice" }] },
          paragraph("Body text."),
          {
            type: "list",
            ordered: false,
            items: [[{ type: "text", value: "one" }], [{ type: "text", value: "two" }]],
          },
          { type: "quote", spans: [{ type: "text", value: "quoted" }] },
        ]}
      />,
    );

    expect(screen.getByRole("heading", { name: "Notice" })).toBeInTheDocument();
    expect(screen.getByText("Body text.")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(container.querySelector("blockquote")).toHaveTextContent("quoted");
  });

  it("renders markup-looking text as characters, never as elements", () => {
    // The payload can only ever say "text", so this is what a hostile body
    // looks like by the time it reaches the browser.
    const { container } = render(
      <AnnouncementBody blocks={[paragraph("<script>alert(1)</script>")]} />,
    );

    expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("iframe")).toBeNull();
  });

  it("opens an external link safely and says so to a screen reader", () => {
    render(
      <AnnouncementBody
        blocks={[
          {
            type: "paragraph",
            spans: [
              { type: "link", value: "the policy", href: "https://onest.test/p" },
            ],
          },
        ]}
      />,
    );

    const link = screen.getByRole("link", { name: /the policy/ });
    expect(link).toHaveAttribute("href", "https://onest.test/p");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveTextContent("opens in a new tab");
  });

  it("keeps a hub-relative link in the same tab", () => {
    render(
      <AnnouncementBody
        blocks={[
          {
            type: "paragraph",
            spans: [{ type: "link", value: "operations", href: "/operations" }],
          },
        ]}
      />,
    );

    const link = screen.getByRole("link", { name: "operations" });
    expect(link).not.toHaveAttribute("target");
  });

  it("renders nothing rather than an empty shell for an empty body", () => {
    const { container } = render(<AnnouncementBody blocks={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a long body in full, without truncating the notice", () => {
    const blocks = Array.from({ length: 60 }, (_, index) =>
      paragraph(`Paragraph ${index}.`),
    );
    render(<AnnouncementBody blocks={blocks} />);

    // An announcement that has been truncated has not been announced.
    expect(screen.getByText("Paragraph 0.")).toBeInTheDocument();
    expect(screen.getByText("Paragraph 59.")).toBeInTheDocument();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(
      <AnnouncementBody
        blocks={[
          { type: "heading", level: 2, spans: [{ type: "text", value: "Notice" }] },
          paragraph("Body text."),
        ]}
      />,
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
