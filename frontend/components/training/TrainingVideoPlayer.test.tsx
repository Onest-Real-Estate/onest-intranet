import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

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

  it("seeks when a transcript line is clicked", async () => {
    const user = userEvent.setup();
    const postMessage = vi.fn();
    render(
      <TrainingVideoPlayer
        embed={{
          url: "https://www.youtube.com/watch?v=abc12345678",
          provider: "youtube",
          host: "www.youtube.com",
          available: true,
        }}
        transcription={{
          segments: [{ startMs: 65000, endMs: 70000, text: "important point" }],
          hasSearchableText: true,
        }}
      />,
    );
    const iframe = document.getElementById("training-video-embed") as HTMLIFrameElement;
    Object.defineProperty(iframe, "contentWindow", {
      configurable: true,
      value: { postMessage },
    });

    await user.click(screen.getByRole("button", { name: /important point/i }));
    expect(postMessage).toHaveBeenCalled();
  });
});
