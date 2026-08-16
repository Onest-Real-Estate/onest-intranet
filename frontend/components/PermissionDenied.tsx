import { Link } from "@inertiajs/react";
import { ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";

/**
 * Custom "permission denied" content, rendered by `PermissionRequired` (or on
 * its own). Layout-free so it renders correctly inside any page; the
 * full-page version for real 403s is registered as an Inertia page in
 * `frontend/pages/PermissionDenied.tsx`.
 */
export function PermissionDenied() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6 py-20 text-center">
      <ShieldAlert className="size-12 text-destructive" aria-hidden />
      <h1 className="text-3xl font-semibold tracking-tight">Permission denied</h1>
      <p className="max-w-md text-muted-foreground">
        You don't have the required permission to view this page. Contact an
        administrator if you believe this is a mistake.
      </p>
      <Button asChild>
        <Link href={routes.home()}>Back to home</Link>
      </Button>
    </div>
  );
}
