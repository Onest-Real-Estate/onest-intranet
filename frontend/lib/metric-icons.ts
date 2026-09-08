import type { LucideIcon } from "lucide-react";
import {
  AlarmClock,
  ArrowLeftRight,
  CalendarCheck2,
  ChartNoAxesColumn,
  CircleDollarSign,
  FilePenLine,
  ListChecks,
  Package,
  ShieldAlert,
  UserPlus,
} from "lucide-react";

/**
 * The approved marks a dashboard metric card may draw.
 *
 * Keys are the `icon` values the backend metric registry ships
 * (`apps/web/metrics.py`), so the card's glyph is reviewed data rather than a
 * lookup on a label. An unknown key falls back to a neutral column chart —
 * never to nothing, and never to an invented mark.
 */
const METRIC_ICONS: Record<string, LucideIcon> = {
  transactions: ArrowLeftRight,
  closings: CalendarCheck2,
  commission: CircleDollarSign,
  tasks: ListChecks,
  "follow-ups": AlarmClock,
  leads: UserPlus,
  contracts: FilePenLine,
  inventory: Package,
  utilization: ChartNoAxesColumn,
  "new-agents": UserPlus,
  compliance: ShieldAlert,
};

export function metricIcon(key: string): LucideIcon {
  return METRIC_ICONS[key] ?? ChartNoAxesColumn;
}
