import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { DashboardProfile } from "@/lib/dashboard/profiles";

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
  onSelect,
}: {
  profiles: DashboardProfile[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  if (profiles.length < 2) {
    return null;
  }

  return (
    <Select value={activeId} onValueChange={onSelect}>
      <SelectTrigger
        id="dashboard-profile"
        aria-label="Dashboard view"
        className="w-full sm:w-56"
      >
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
  );
}
