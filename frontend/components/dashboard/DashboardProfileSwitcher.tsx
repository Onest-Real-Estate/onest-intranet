import { LayoutGrid } from "lucide-react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { DashboardProfile } from "@/lib/dashboard/profiles";
import type { DashboardProfileSource } from "@/lib/dashboard/resolve";

/** How the reader arrived at the profile they are looking at. */
const sourceLabel: Record<DashboardProfileSource, string> = {
  "reader-selection": "Your choice",
  "user-assignment": "Assigned to you",
  "primary-role": "Your primary role",
  "effective-role": "Your role",
  "scope-assignment": "Assigned to your office",
  fallback: "Default",
};

/**
 * Switch between the dashboard presentations the reader is authorized for.
 *
 * The control is presentation only. Picking a profile reorders and filters the
 * widgets on this page; it adds no permission, widens no scope, and sends
 * nothing to the server. Every widget is still permission-filtered after the
 * switch, and every provider re-checks on its own.
 *
 * Nothing renders when there is only one authorized profile — a select with a
 * single option is a control that cannot be used.
 */
export function DashboardProfileSwitcher({
  profiles,
  activeId,
  source,
  onSelect,
}: {
  profiles: DashboardProfile[];
  activeId: string;
  source: DashboardProfileSource;
  onSelect: (id: string) => void;
}) {
  if (profiles.length < 2) {
    return null;
  }
  const active = profiles.find((profile) => profile.id === activeId);

  return (
    <div className="flex min-w-0 flex-col gap-1">
      <Select value={activeId} onValueChange={onSelect}>
        <SelectTrigger
          id="dashboard-profile"
          aria-label="Dashboard view"
          className="w-full"
        >
          <LayoutGrid className="text-muted-foreground size-4" aria-hidden />
          <SelectValue placeholder="Choose a dashboard" />
        </SelectTrigger>
        <SelectContent>
          {profiles.map((profile) => (
            <SelectItem key={profile.id} value={profile.id}>
              {profile.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="text-muted-foreground line-clamp-2 px-1 text-xs leading-5">
        {sourceLabel[source]}
        {active ? ` · ${active.description}` : ""}
      </p>
    </div>
  );
}
