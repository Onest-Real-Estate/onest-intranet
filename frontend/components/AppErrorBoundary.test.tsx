import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import {
  AppErrorBoundary,
  isChunkLoadError,
  RecoverableError,
} from "@/components/AppErrorBoundary";

const routerReload = vi.hoisted(() => vi.fn());

vi.mock("@inertiajs/react", () => ({
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { reload: routerReload },
}));

beforeEach(() => {
  routerReload.mockClear();
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});

it("recovers from a render failure through a fresh Inertia reload", async () => {
  function Broken(): ReactNode {
    throw new Error("chunk failed");
  }

  render(
    <AppErrorBoundary>
      <Broken />
    </AppErrorBoundary>,
    { onCaughtError: () => undefined },
  );
  expect(
    screen.getByRole("heading", { name: "This page couldn’t load" }),
  ).toBeVisible();

  await userEvent.click(screen.getByRole("button", { name: "Try again" }));

  expect(routerReload).toHaveBeenCalledWith({ fresh: true });
});

it("renders an accessible recovery pattern", async () => {
  const { container } = render(<RecoverableError onRetry={() => undefined} />);
  expect(await axe(container)).toHaveNoViolations();
});

it("recognizes chunk failures without treating ordinary errors as chunks", () => {
  expect(
    isChunkLoadError(new Error("Failed to fetch dynamically imported module")),
  ).toBe(true);
  expect(isChunkLoadError(new Error("Validation failed"))).toBe(false);
});

it("recovers when a route chunk rejects after the app mounted", () => {
  render(
    <AppErrorBoundary>
      <p>Current page</p>
    </AppErrorBoundary>,
  );
  const rejection = new Event("unhandledrejection", { cancelable: true });
  Object.defineProperty(rejection, "reason", {
    value: new Error("ChunkLoadError: loading chunk 12 failed"),
  });

  act(() => window.dispatchEvent(rejection));

  expect(
    screen.getByRole("heading", { name: "This page couldn’t load" }),
  ).toBeVisible();
});
