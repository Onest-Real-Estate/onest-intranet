import { usePage } from "@inertiajs/react";
import type { ReactNode } from "react";

import { PermissionDenied } from "@/components/PermissionDenied";
import { hasPermission, type PermissionCheck } from "@/lib/permissions";
import type { PageProps } from "@/types";

export type { PermissionCheck } from "@/lib/permissions";
export { hasPermission } from "@/lib/permissions";

interface PermissionRequiredProps {
  /** Permissions required to render `children`. Defaults to no requirements. */
  permission?: PermissionCheck;
  /**
   * When the user lacks the permission: render nothing instead of the denied
   * page (used with `raise={false}`).
   */
  hideChild?: boolean;
  /**
   * When the user lacks the permission: render the custom permission denied
   * page instead of `children`. Takes precedence over `hideChild`.
   */
  raise?: boolean;
  children?: ReactNode;
}

export function PermissionRequired({
  permission = {},
  hideChild = false,
  raise = true,
  children,
}: PermissionRequiredProps) {
  const { user } = usePage<PageProps>().props;

  if (hasPermission(user, permission)) {
    return <>{children}</>;
  }
  if (raise) {
    return <PermissionDenied />;
  }
  if (hideChild) {
    return null;
  }
  return <>{children}</>;
}
