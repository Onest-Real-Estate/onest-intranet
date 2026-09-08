import { router } from "@inertiajs/react";

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
}: {
  options: DashboardScopeOption[];
  selectedKey: string | null;
  /** Widget props to re-request when the scope changes. */
  reloadProps: DashboardWidgetProp[];
}) {
  const current = options.find((option) => option.key === selectedKey) ?? options[0];

  if (options.length < 2) {
    return current ? (
      <p className="text-muted-foreground text-sm">{current.label}</p>
    ) : null;
  }

  function change(key: string) {
    if (reloadProps.length === 0) {
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
        className="w-full sm:w-56"
      >
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
