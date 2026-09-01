import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { TrainingVideoPlayer } from "@/components/training/TrainingVideoPlayer";

describe("TrainingVideoPlayer", () => {
  it("filters transcript matches and exposes seek controls", async () => {
    const user = userEvent.setup();
    render(
      <TrainingVideoPlayer
        embed={{
          url: "https://www.youtube.com/watch?v=abc12345678",
          provider: "youtube",
          host: "www.youtube.com",
          available: true,
        }}
        transcription={{
          segments: [
            { startMs: 1000, endMs: 4000, text: "how to fill out Form 21" },
            { startMs: 5000, endMs: 8000, text: "inspection contingencies" },
          ],
          hasSearchableText: true,
        }}
      />,
    );

    expect(screen.getByText("how to fill out Form 21")).toBeInTheDocument();
    await user.type(
      screen.getByRole("searchbox", { name: "Search transcript" }),
      "Form 21",
    );
    expect(screen.getByText("how to fill out Form 21")).toBeInTheDocument();
    expect(screen.queryByText("inspection contingencies")).not.toBeInTheDocument();
  });
});
