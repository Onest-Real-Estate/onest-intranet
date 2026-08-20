import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProfilePhotoPanel } from "@/components/profile/ProfilePhotoPanel";
import type { ProfileLimits } from "@/types";

const limits: ProfileLimits = {
  headshotMaxBytes: 5 * 1024 * 1024,
  headshotMinDimension: 200,
  bioMaxLength: 1500,
  maxLanguages: 10,
};

function panel(headshotUrl: string | null = null) {
  return (
    <ProfilePhotoPanel
      headshotUrl={headshotUrl}
      displayName="Bobby Lee"
      csrfToken="token"
      limits={limits}
    />
  );
}

function jsonResponse(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: async () => body,
  } as Response;
}

function pngFile() {
  return new File(["fake"], "headshot.png", { type: "image/png" });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ProfilePhotoPanel", () => {
  it("states the server's constraints and falls back to initials", () => {
    render(panel());
    expect(screen.getByText("Bobby Lee")).toBeInTheDocument();
    expect(screen.getByText("No photo yet")).toBeInTheDocument();
    expect(
      screen.getByText("JPEG or PNG · at least 200×200 px · max 5 MB"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remove photo/i })).toBeNull();
  });

  it("uploads to the self-only endpoint and reports success", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ url: "/media/headshots/new.png" }));
    vi.stubGlobal("fetch", fetchMock);

    render(panel());
    await user.upload(screen.getByLabelText(/choose file/i), pngFile());

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/account/headshot");
    expect(init.method).toBe("POST");
    const body = init.body as FormData;
    expect(body.get("csrfmiddlewaretoken")).toBe("token");
    expect(body.get("headshot")).toBeInstanceOf(File);

    expect(await screen.findByText("Upload complete")).toBeInTheDocument();
    expect(screen.getByText("Profile photo updated.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /remove photo/i })).toBeVisible();
  });

  it("shows the server's rejection message and offers a retry", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(
            { error: "Headshot must be at least 200×200 pixels." },
            false,
            422,
          ),
        ),
    );

    render(panel());
    await user.upload(screen.getByLabelText(/choose file/i), pngFile());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Headshot must be at least 200×200 pixels.");
    expect(screen.getByRole("button", { name: /retry/i })).toBeVisible();
  });

  it("rejects an oversized file before it reaches the network", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(panel());
    await user.upload(
      screen.getByLabelText(/choose file/i),
      new File([new ArrayBuffer(limits.headshotMaxBytes + 1)], "huge.png", {
        type: "image/png",
      }),
    );

    expect(fetchMock).not.toHaveBeenCalled();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Choose a file smaller than/i,
    );
  });

  it("removes the stored photo through the same endpoint", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ url: null }));
    vi.stubGlobal("fetch", fetchMock);

    render(panel("/media/headshots/old.png"));
    expect(screen.getByText("Photo on file")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /remove photo/i }));

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/account/headshot");
    expect((init.body as FormData).get("remove")).toBe("1");
    expect(await screen.findByText("No photo yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remove photo/i })).toBeNull();
  });

  it("keeps the photo and explains the failure when removal fails", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({}, false, 500)));

    render(panel("/media/headshots/old.png"));
    await user.click(screen.getByRole("button", { name: /remove photo/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The photo could not be removed. Try again.",
    );
    expect(screen.getByText("Photo on file")).toBeInTheDocument();
  });
});
