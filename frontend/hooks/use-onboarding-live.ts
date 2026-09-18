import { router } from "@inertiajs/react";
import { Centrifuge } from "centrifuge";
import { useCallback, useEffect, useRef, useState } from "react";

import { parseOnboardingInvalidation } from "@/lib/onboarding/live";
import { routes } from "@/lib/routes";
import type { AgentOnboardingJourney } from "@/types";

interface Credentials {
  url: string;
  channel: string;
  connectionToken: string;
  subscriptionToken: string;
}

type LiveStatus = "fresh" | "delayed";
const FAILURE_NOTICE_MS = 15_000;
const BATCH_MS = 180;
const MIN_RELOAD_MS = 1_000;

async function credentials(): Promise<Credentials> {
  const response = await fetch(routes.onboarding_stream_token(), {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (response.status === 401 || response.status === 403) {
    throw new Centrifuge.UnauthorizedError("Onboarding access changed");
  }
  if (!response.ok) throw new Error("Onboarding live updates unavailable");
  return (await response.json()) as Credentials;
}

/** Centrifugo carries hints only. Every refresh reconstructs the journey in Django. */
export function useOnboardingLive(
  journey: AgentOnboardingJourney | undefined,
  authorizationVersion: string | undefined,
) {
  const [status, setStatus] = useState<LiveStatus>("fresh");
  const [checking, setChecking] = useState(false);
  const [authorizationGeneration, setAuthorizationGeneration] = useState(0);
  const enabled = journey?.stateVersion !== undefined;
  const loadedVersion = useRef(journey?.stateVersion ?? 0);
  const requestedVersion = useRef(loadedVersion.current);
  const inFlight = useRef(false);
  const lastReloadAt = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scheduleRef = useRef<() => void>(() => undefined);
  const failureTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(true);
  const catchupAttempts = useRef(0);

  useEffect(() => {
    loadedVersion.current = Math.max(loadedVersion.current, journey?.stateVersion ?? 0);
  }, [journey?.stateVersion]);

  const refresh = useCallback(() => {
    if (!mounted.current || inFlight.current || !enabled) return;
    const remaining = MIN_RELOAD_MS - (Date.now() - lastReloadAt.current);
    if (remaining > 0) {
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => refresh(), remaining);
      return;
    }
    inFlight.current = true;
    setChecking(true);
    lastReloadAt.current = Date.now();
    const focused = document.activeElement;
    router.reload({
      only: ["onboardingJourney"],
      // Inertia reload preserves component state and scroll by default.
      showProgress: false,
      onSuccess: (page) => {
        const next = (page.props as { onboardingJourney?: AgentOnboardingJourney })
          .onboardingJourney;
        if (next)
          loadedVersion.current = Math.max(
            loadedVersion.current,
            next.stateVersion ?? 0,
          );
        if (loadedVersion.current >= requestedVersion.current)
          catchupAttempts.current = 0;
      },
      onFinish: () => {
        inFlight.current = false;
        setChecking(false);
        const currentFocus = document.activeElement;
        if (
          focused instanceof HTMLElement &&
          focused.isConnected &&
          (currentFocus === document.body || !currentFocus?.isConnected)
        ) {
          focused.focus({ preventScroll: true });
        }
        if (requestedVersion.current > loadedVersion.current) {
          catchupAttempts.current += 1;
          if (catchupAttempts.current <= 3) scheduleRef.current();
          else setStatus("delayed");
        }
      },
      onError: () => setStatus("delayed"),
    });
  }, [enabled]);

  const schedule = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => refresh(), BATCH_MS);
  }, [refresh]);
  scheduleRef.current = schedule;

  // biome-ignore lint/correctness/useExhaustiveDependencies: A server-owned authorization change must tear down the old Centrifugo credentials.
  useEffect(() => {
    if (!enabled) return;
    mounted.current = true;
    let stopped = false;
    let client: Centrifuge | null = null;
    let attempts = 0;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let previouslyConnected = false;
    let hadFailure = false;

    const markFailure = () => {
      if (failureTimer.current) return;
      failureTimer.current = setTimeout(() => {
        if (!stopped) {
          hadFailure = true;
          setStatus("delayed");
        }
      }, FAILURE_NOTICE_MS);
    };
    const markFresh = () => {
      if (failureTimer.current) clearTimeout(failureTimer.current);
      failureTimer.current = null;
      setStatus("fresh");
    };
    const connect = async () => {
      try {
        const initial = await credentials();
        if (stopped) return;
        client = new Centrifuge(initial.url, {
          token: initial.connectionToken,
          getToken: async () => (await credentials()).connectionToken,
          minReconnectDelay: 1_000,
          maxReconnectDelay: 30_000,
        });
        const subscription = client.newSubscription(initial.channel, {
          token: initial.subscriptionToken,
          getToken: async () => (await credentials()).subscriptionToken,
          minResubscribeDelay: 1_000,
          maxResubscribeDelay: 30_000,
        });
        subscription.on("publication", ({ data }) => {
          const event = parseOnboardingInvalidation(data);
          if (!event || event.stateVersion <= requestedVersion.current) return;
          requestedVersion.current = Math.max(
            requestedVersion.current,
            event.stateVersion,
          );
          catchupAttempts.current = 0;
          if (["office", "ownership", "account", "access"].includes(event.sourceKey)) {
            setAuthorizationGeneration((value) => value + 1);
          }
          schedule();
        });
        client.on("connected", () => {
          const needsCatchup =
            hadFailure || previouslyConnected || authorizationGeneration > 0;
          markFresh();
          hadFailure = false;
          if (needsCatchup) schedule();
          previouslyConnected = true;
        });
        client.on("connecting", markFailure);
        client.on("disconnected", () => {
          hadFailure = true;
          markFailure();
        });
        subscription.on("subscribing", markFailure);
        subscription.on("subscribed", markFresh);
        subscription.subscribe();
        client.connect();
      } catch (error) {
        if (stopped) return;
        markFailure();
        if (error instanceof Centrifuge.UnauthorizedError) return;
        attempts += 1;
        const maxDelay = Math.min(30_000, 1_000 * 2 ** Math.min(attempts, 5));
        retryTimer = setTimeout(connect, maxDelay / 2 + (Math.random() * maxDelay) / 2);
      }
    };
    void connect();
    const pagehide = () => client?.disconnect();
    window.addEventListener("pagehide", pagehide);
    return () => {
      stopped = true;
      mounted.current = false;
      window.removeEventListener("pagehide", pagehide);
      if (retryTimer) clearTimeout(retryTimer);
      if (timer.current) clearTimeout(timer.current);
      if (failureTimer.current) clearTimeout(failureTimer.current);
      client?.disconnect();
    };
  }, [enabled, authorizationVersion, authorizationGeneration, schedule]);

  return { status, checking, checkForUpdates: refresh };
}
