import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";

import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
  SurfaceCardMeta,
} from "@/components/design-system/surface-card";

describe("PanelHeader", () => {
  it("renders the title as a real heading with meta and action slots", () => {
    render(
      <SurfaceCard>
        <PanelHeader
          title="Action items"
          description="What needs you next."
          meta={<SurfaceCardMeta>2 of 5 open</SurfaceCardMeta>}
          action={<button type="button">Manage</button>}
        />
        <SurfaceCardContent>Body</SurfaceCardContent>
      </SurfaceCard>,
    );

    expect(
      screen.getByRole("heading", { level: 2, name: "Action items" }),
    ).toBeVisible();
    expect(screen.getByText("What needs you next.")).toBeVisible();
    expect(screen.getByText("2 of 5 open")).toBeVisible();
    expect(screen.getByRole("button", { name: "Manage" })).toBeVisible();
  });

  it("honours an explicit heading level so panels fit the document outline", () => {
    render(
      <SurfaceCard>
        <PanelHeader title="Nested panel" headingLevel="h3" />
      </SurfaceCard>,
    );
    expect(
      screen.getByRole("heading", { level: 3, name: "Nested panel" }),
    ).toBeVisible();
  });

  it("marks a loading surface as busy", () => {
    const { container } = render(
      <SurfaceCard state="loading">
        <PanelHeader title="Loading panel" />
      </SurfaceCard>,
    );
    expect(container.querySelector("[data-slot=card]")).toHaveAttribute(
      "aria-busy",
      "true",
    );
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(
      <main>
        <h1>Page</h1>
        <SurfaceCard>
          <PanelHeader
            title="Active transactions"
            meta={<SurfaceCardMeta>4 open</SurfaceCardMeta>}
          />
          <SurfaceCardContent>Body</SurfaceCardContent>
        </SurfaceCard>
      </main>,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
