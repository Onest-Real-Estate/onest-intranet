import { Link, router } from "@inertiajs/react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Component, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";

export function RecoverableError({
  onRetry,
  title = "This page couldn’t load",
}: {
  onRetry: () => void;
  title?: string;
}) {
  return (
    <main className="bg-background flex min-h-svh items-center justify-center px-6 py-16">
      <div className="grid w-full max-w-md justify-items-center gap-5 text-center">
        <span className="bg-chip-destructive text-destructive grid size-12 place-items-center rounded-lg">
          <AlertTriangle aria-hidden className="size-6" />
        </span>
        <div className="grid gap-2">
          <h1 className="text-2xl font-semibold tracking-[-0.02em]">{title}</h1>
          <p className="text-muted-foreground text-sm leading-6">
            Your work is still safe. Try loading the page again, or return to the
            dashboard if the problem continues.
          </p>
        </div>
        <div className="flex flex-wrap justify-center gap-2">
          <Button type="button" onClick={onRetry}>
            <RefreshCw aria-hidden className="size-4" />
            Try again
          </Button>
          <Button asChild variant="outline">
            <Link href={routes.dashboard()}>Go to dashboard</Link>
          </Button>
        </div>
      </div>
    </main>
  );
}

interface AppErrorBoundaryState {
  failed: boolean;
}

export function isChunkLoadError(reason: unknown): boolean {
  const message = reason instanceof Error ? reason.message : String(reason);
  return /chunkloaderror|dynamically imported module|importing a module script failed|loading chunk/i.test(
    message,
  );
}

/** Last-resort recovery for render and asynchronously loaded chunk failures. */
export class AppErrorBoundary extends Component<
  { children: ReactNode },
  AppErrorBoundaryState
> {
  state: AppErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): AppErrorBoundaryState {
    return { failed: true };
  }

  componentDidMount() {
    window.addEventListener("error", this.onWindowError);
    window.addEventListener("unhandledrejection", this.onUnhandledRejection);
  }

  componentWillUnmount() {
    window.removeEventListener("error", this.onWindowError);
    window.removeEventListener("unhandledrejection", this.onUnhandledRejection);
  }

  onWindowError = (event: ErrorEvent) => {
    if (isChunkLoadError(event.error ?? event.message)) {
      event.preventDefault();
      this.setState({ failed: true });
    }
  };

  onUnhandledRejection = (event: PromiseRejectionEvent) => {
    if (isChunkLoadError(event.reason)) {
      event.preventDefault();
      this.setState({ failed: true });
    }
  };

  retry = () => {
    router.reload({ fresh: true });
  };

  render() {
    if (this.state.failed) {
      return <RecoverableError onRetry={this.retry} />;
    }
    return this.props.children;
  }
}
