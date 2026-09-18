import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useOnboardingLive } from "@/hooks/use-onboarding-live";
import { agentJourney } from "@/test/onboarding";

const mocks = vi.hoisted(() => {
  class Emitter {
    handlers = new Map<string, (...args: never[]) => void>();
    on(name: string, handler: (...args: never[]) => void) {
      this.handlers.set(name, handler);
      return this;
    }
    emit(name: string, value?: unknown) {
      this.handlers.get(name)?.(value as never);
    }
  }
  class Subscription extends Emitter {
    subscribe = vi.fn();
  }
  class Client extends Emitter {
    static UnauthorizedError = class extends Error {};
    subscription = new Subscription();
    newSubscription = vi.fn(() => this.subscription);
    connect = vi.fn();
    disconnect = vi.fn();
  }
  return { Client, instances: [] as InstanceType<typeof Client>[], reload: vi.fn() };
});

vi.mock("centrifuge", () => ({
  Centrifuge: class extends mocks.Client {
    constructor(..._args: never[]) {
      super();
      mocks.instances.push(this);
    }
  },
}));
vi.mock("@inertiajs/react", () => ({ router: { reload: mocks.reload } }));

const credentials = {
  url: "ws://centrifugo.test/connection/websocket",
  channel: "$onboarding:opaque",
  connectionToken: "connection",
  subscriptionToken: "subscription",
};
const uuid = "facdb737-47aa-45e4-99a7-835c73973ff5";

async function settle() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  mocks.instances.length = 0;
  mocks.reload.mockReset();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, json: async () => credentials })),
  );
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("onboarding live invalidation", () => {
  it("batches rapid events, ignores old versions, and reloads only the journey", async () => {
    const journey = agentJourney({ stateVersion: 1 });
    const { unmount } = renderHook(() => useOnboardingLive(journey, "scope-1"));
    await settle();
    const client = mocks.instances[0];
    expect(client.newSubscription).toHaveBeenCalledWith(
      credentials.channel,
      expect.objectContaining({ token: credentials.subscriptionToken }),
    );
    act(() => {
      client.subscription.emit("publication", {
        data: {
          id: uuid,
          eventType: "onboarding.state_changed",
          sourceKey: "tool",
          stateVersion: 3,
        },
      });
      client.subscription.emit("publication", {
        data: {
          id: uuid,
          eventType: "onboarding.state_changed",
          sourceKey: "tool",
          stateVersion: 2,
        },
      });
      client.subscription.emit("publication", {
        data: {
          id: uuid,
          eventType: "onboarding.state_changed",
          sourceKey: "tool",
          stateVersion: 3,
        },
      });
    });
    await act(async () => vi.advanceTimersByTimeAsync(180));
    expect(mocks.reload).toHaveBeenCalledTimes(1);
    const options = mocks.reload.mock.calls[0][0];
    expect(options.only).toEqual(["onboardingJourney"]);
    expect(options.showProgress).toBe(false);
    act(() => {
      options.onSuccess({ props: { onboardingJourney: { stateVersion: 3 } } });
      options.onFinish();
    });
    await act(async () => vi.advanceTimersByTimeAsync(2_000));
    expect(mocks.reload).toHaveBeenCalledTimes(1);
    act(() =>
      client.subscription.emit("publication", {
        data: {
          id: uuid,
          eventType: "onboarding.state_changed",
          sourceKey: "tool",
          stateVersion: 2,
        },
      }),
    );
    await act(async () => vi.advanceTimersByTimeAsync(200));
    expect(mocks.reload).toHaveBeenCalledTimes(1);
    unmount();
    expect(client.disconnect).toHaveBeenCalled();
  });

  it("preserves focus and reloads after a reconnect or manual check", async () => {
    const input = document.createElement("input");
    document.body.append(input);
    input.focus();
    const { result, unmount } = renderHook(() =>
      useOnboardingLive(agentJourney({ stateVersion: 1 }), "scope-1"),
    );
    await settle();
    const client = mocks.instances[0];
    act(() => client.emit("connected"));
    act(() => client.emit("disconnected"));
    act(() => client.emit("connected"));
    await act(async () => vi.advanceTimersByTimeAsync(180));
    expect(mocks.reload).toHaveBeenCalledTimes(1);
    const other = document.createElement("button");
    document.body.append(other);
    other.focus();
    act(() => mocks.reload.mock.calls[0][0].onFinish());
    expect(document.activeElement).toBe(other);
    act(() => result.current.checkForUpdates());
    await act(async () => vi.advanceTimersByTimeAsync(1_000));
    expect(mocks.reload).toHaveBeenCalledTimes(2);
    unmount();
    input.remove();
    other.remove();
  });

  it("reloads again when a newer event arrives during an older response", async () => {
    const { unmount } = renderHook(() =>
      useOnboardingLive(agentJourney({ stateVersion: 1 }), "scope-1"),
    );
    await settle();
    const client = mocks.instances[0];
    act(() =>
      client.subscription.emit("publication", {
        data: {
          id: uuid,
          eventType: "onboarding.state_changed",
          sourceKey: "contract",
          stateVersion: 3,
        },
      }),
    );
    await act(async () => vi.advanceTimersByTimeAsync(180));
    const first = mocks.reload.mock.calls[0][0];
    act(() =>
      client.subscription.emit("publication", {
        data: {
          id: uuid,
          eventType: "onboarding.state_changed",
          sourceKey: "tool",
          stateVersion: 4,
        },
      }),
    );
    act(() => {
      first.onSuccess({ props: { onboardingJourney: { stateVersion: 3 } } });
      first.onFinish();
    });
    await act(async () => vi.advanceTimersByTimeAsync(1_000));
    expect(mocks.reload).toHaveBeenCalledTimes(2);
    unmount();
  });

  it("shows delayed status only after a prolonged outage and cleans up", async () => {
    const { result, unmount } = renderHook(() =>
      useOnboardingLive(agentJourney({ stateVersion: 1 }), "scope-1"),
    );
    await settle();
    const client = mocks.instances[0];
    act(() => client.emit("disconnected"));
    await act(async () => vi.advanceTimersByTimeAsync(14_999));
    expect(result.current.status).toBe("fresh");
    await act(async () => vi.advanceTimersByTimeAsync(1));
    expect(result.current.status).toBe("delayed");
    act(() => client.emit("connected"));
    expect(result.current.status).toBe("fresh");
    unmount();
    expect(client.disconnect).toHaveBeenCalled();
  });

  it("rechecks authorization after an office event", async () => {
    const { unmount } = renderHook(() =>
      useOnboardingLive(agentJourney({ stateVersion: 1 }), "scope-1"),
    );
    await settle();
    const first = mocks.instances[0];
    act(() => {
      first.subscription.emit("publication", {
        data: {
          id: uuid,
          eventType: "onboarding.state_changed",
          sourceKey: "office",
          stateVersion: 2,
        },
      });
    });
    await settle();
    expect(first.disconnect).toHaveBeenCalled();
    expect(mocks.instances).toHaveLength(2);
    unmount();
  });

  it("backs off failed credentials with jitter and keeps manual refresh usable", async () => {
    const random = vi.spyOn(Math, "random").mockReturnValue(0);
    let attempts = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        attempts += 1;
        if (attempts < 3) throw new Error("provider unavailable");
        return { ok: true, json: async () => credentials };
      }),
    );
    const { result, unmount } = renderHook(() =>
      useOnboardingLive(agentJourney({ stateVersion: 1 }), "scope-1"),
    );
    await settle();
    expect(attempts).toBe(1);
    act(() => result.current.checkForUpdates());
    expect(mocks.reload).toHaveBeenCalledTimes(1);
    await act(async () => vi.advanceTimersByTimeAsync(999));
    expect(attempts).toBe(1);
    await act(async () => vi.advanceTimersByTimeAsync(1));
    expect(attempts).toBe(2);
    await act(async () => vi.advanceTimersByTimeAsync(2_000));
    expect(attempts).toBe(3);
    expect(mocks.instances).toHaveLength(1);
    unmount();
    random.mockRestore();
  });
});
