import type { ReactNode } from "react";

import { HubLayout } from "@/components/HubLayout";
import { PermissionDenied } from "@/components/PermissionDenied";

/**
 * Inertia page wrapper for `PermissionDenied`, registered so Django can
 * render it for real 403s — see apps/web/views.py `permission_denied` and
 * `handler403` in config/urls.py.
 */
export default function PermissionDeniedPage() {
  return <PermissionDenied />;
}

PermissionDeniedPage.layout = (page: ReactNode) => <HubLayout>{page}</HubLayout>;
