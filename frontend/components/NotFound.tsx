import { Link } from "@inertiajs/react";
import { SearchX } from "lucide-react";

import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";

export function NotFound({ requestId }: { requestId?: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6 py-20 text-center">
      <SearchX
        className="size-12 text-muted-foreground"
        strokeWidth={1.5}
        aria-hidden
      />
      <h1 className="text-3xl font-semibold tracking-tight">Page not found</h1>
      <p className="max-w-md text-muted-foreground">
        The page you're looking for doesn't exist or is no longer available from this
        location.
      </p>
      {requestId ? (
        <p className="text-muted-foreground rounded-md border px-3 py-2 text-xs">
          Request ID: {requestId}
        </p>
      ) : null}
      <Button asChild>
        <Link href={routes.dashboard()}>Back to dashboard</Link>
      </Button>
    </div>
  );
}
