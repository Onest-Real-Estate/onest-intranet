import { router } from "@inertiajs/react";
import { Building2 } from "lucide-react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { DashboardScopeOption, DashboardWidgetProp } from "@/types";

/**
 * Choose which office or region the administrative widgets report on.
 *
 * The list is composed server-side from the reader's effective access, so it
 * can only ever contain breadths they already read at. The selected key is
 * sent back and **revalidated server-side** on every request — a forged or
 * remembered key buys nothing, and no office or region primary key is ever
 * accepted from the client.
 *
 * When only one scope is available there is nothing to choose, so the page
 * shows the scope as a plain label rather than a control that does nothing.
 */
export function DashboardScopeSelector({
  options,
  selectedKey,
  reloadProps,
  onSelect,
  interactive = true,
}: {
  options: DashboardScopeOption[];
  selectedKey: string | null;
  /** Widget props to re-request when the scope changes. */
  reloadProps: DashboardWidgetProp[];
  onSelect?: (key: string) => void;
  /**
   * False while the scope is illustrative (no server `scope` prop yet): the
   * selector relabels the page but asks the server for nothing.
   */
  interactive?: boolean;
}) {
  const current = options.find((option) => option.key === selectedKey) ?? options[0];

  if (options.length < 2) {
    return current ? (
      <p className="text-muted-foreground flex items-center gap-1.5 text-sm">
        <Building2 className="size-4 shrink-0" aria-hidden />
        <span>{current.label}</span>
      </p>
    ) : null;
  }

  function change(key: string) {
    onSelect?.(key);
    if (!interactive || reloadProps.length === 0) {
      return;
    }
    // Only the scoped widgets are re-requested; the shell and the reader's own
    // figures do not change with the selection.
    router.reload({ only: reloadProps, data: { scope: key } });
  }

  return (
    <Select value={current?.key} onValueChange={change}>
      <SelectTrigger
        id="dashboard-scope"
        aria-label="Reporting scope"
        className="w-full"
      >
        <Building2 className="text-muted-foreground size-4" aria-hidden />
        <SelectValue placeholder="Choose a scope" />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.key} value={option.key}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
