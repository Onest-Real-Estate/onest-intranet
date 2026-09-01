import type { TrainingFilters, TrainingPresentationBadge } from "@/types";

export function activeFilterCount(filters: TrainingFilters): number {
  return (
    Number(Boolean(filters.category)) +
    Number(Boolean(filters.type)) +
    Number(Boolean(filters.required)) +
    Number(Boolean(filters.tool)) +
    Number(Boolean(filters.completion)) +
    Number(filters.view !== "all") +
    Number(Boolean(filters.q))
  );
}

export function rejectedFilterMessage(filters: TrainingFilters): string | null {
  if (!filters.rejected?.length) {
    return null;
  }
  return "Some filters were ignored because they were not recognized.";
}

export function contentTypePresentation(
  badge: TrainingPresentationBadge,
): TrainingPresentationBadge & { srLabel: string } {
  return {
    ...badge,
    srLabel: badge.known ? badge.label : `Unknown type: ${badge.label}`,
  };
}

export function completionPresentation(status: string): {
  label: string;
  tone: "neutral" | "info" | "success" | "warning";
} {
  if (status === "completed") {
    return { label: "Completed", tone: "success" };
  }
  if (status === "in_progress") {
    return { label: "In progress", tone: "info" };
  }
  return { label: "Not started", tone: "neutral" };
}

export function formatDuration(minutes: number | null): string | null {
  if (!minutes || minutes <= 0) {
    return null;
  }
  if (minutes < 60) {
    return `~${minutes} min`;
  }
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  if (remainder === 0) {
    return `~${hours} hr`;
  }
  return `~${hours} hr ${remainder} min`;
}
