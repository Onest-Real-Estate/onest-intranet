import {
  CircleAlert,
  CircleCheck,
  CircleHelp,
  Clock3,
  FileSignature,
  Info,
} from "lucide-react";

import type { StatusPresentation } from "@/types/design-system";

export const TRANSACTION_STATUS: Record<string, StatusPresentation> = {
  on_track: { label: "On track", tone: "success", icon: CircleCheck },
  action_needed: {
    label: "Action needed",
    tone: "warning",
    icon: CircleAlert,
  },
};

export const CONTRACT_STATUS: Record<string, StatusPresentation> = {
  active: { label: "Active", tone: "info", icon: Info },
  incomplete: { label: "Incomplete", tone: "destructive", icon: CircleAlert },
  pending_signature: {
    label: "Pending signature",
    tone: "warning",
    icon: FileSignature,
  },
  pending_documents: {
    label: "Pending documents",
    tone: "warning",
    icon: Clock3,
  },
  approved: { label: "Approved", tone: "success", icon: CircleCheck },
  settled: { label: "Settled", tone: "success", icon: CircleCheck },
  archived: { label: "Archived", tone: "neutral", icon: Clock3 },
};

const UNKNOWN_STATUS: StatusPresentation = {
  label: "Unknown status",
  tone: "neutral",
  icon: CircleHelp,
};

/** Backend values never become class names. Unknown values fail closed. */
export function presentStatus(
  value: string,
  adapter: Record<string, StatusPresentation>,
): StatusPresentation {
  return adapter[value] ?? UNKNOWN_STATUS;
}
