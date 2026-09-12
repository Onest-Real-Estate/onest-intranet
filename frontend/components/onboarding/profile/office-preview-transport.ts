import type { OnboardingOfficeSelection } from "@/types";

export class OfficePreviewError extends Error {}

export async function loadOfficePreview(
  url: string,
  signal?: AbortSignal,
): Promise<OnboardingOfficeSelection> {
  const response = await fetch(url, {
    method: "GET",
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new OfficePreviewError(
      response.status === 404
        ? "That office is no longer available. Choose another office."
        : "We could not load that office right now. Try again.",
    );
  }
  return (await response.json()) as OnboardingOfficeSelection;
}
