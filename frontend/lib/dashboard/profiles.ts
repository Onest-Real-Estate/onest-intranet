/**
 * Dashboard profiles: reusable, reviewed compositions of registry widget ids.
 *
 * Eleven roles get eleven presentations out of one page. A profile is data —
 * an id, a label, the roles it is the default for, and an ordered list of
 * widget ids — so adding a role's dashboard is a row here, never a new page
 * component and never a conditional in `Dashboard.tsx`.
 *
 * A profile grants nothing. Every widget it lists is still filtered through
 * the reader's Django permissions in `resolve.ts`, and every provider behind
 * those widgets re-applies permissions and scope server-side.
 */

import type { DashboardWidgetId } from "@/lib/dashboard/widget-registry";

export type DashboardProfileId =
  | "agent"
  | "transactionCoordinator"
  | "branchAdmin"
  | "branchManager"
  | "regional"
  | "broker"
  | "compliance"
  | "marketing"
  | "accounting"
  | "itSupport"
  | "systemAdmin"
  | "authenticated";

export interface DashboardProfile {
  id: DashboardProfileId;
  label: string;
  /** One sentence, shown in the profile switcher. */
  description: string;
  /** Stable role codes (`apps/user/roles.py`) this profile is the default for. */
  roleCodes: readonly string[];
  /**
   * Mirrors the role catalog's priority so a multi-role reader lands on the
   * same profile the rest of the stack considers their most senior. Lower wins.
   */
  priority: number;
  /**
   * Layout order. Duplicates are dropped during resolution.
   *
   * Every profile leads with `performance` — the four-figure metrics row is
   * the first thing after the greeting, in every role. `announcements` and
   * `quickAccess` follow as an adjacent pair: they share the twelve-column
   * band, so they have to be adjacent for the row to close.
   */
  widgets: readonly DashboardWidgetId[];
}

/**
 * Every reader gets this much: their own book of business and the brokerage's
 * news. It is the last step of resolution, so an authenticated user with no
 * catalogued role still opens a working dashboard rather than a blank page.
 */
const AUTHENTICATED_WIDGETS: readonly DashboardWidgetId[] = [
  "performance",
  "announcements",
  "quickAccess",
  "myDay",
  "training",
  "quickDocuments",
];

export const DASHBOARD_PROFILES: readonly DashboardProfile[] = [
  {
    id: "systemAdmin",
    label: "System Admin",
    description: "Platform health, people administration, and company-wide operations.",
    roleCodes: ["system_admin"],
    priority: 0,
    widgets: [
      "performance",
      "announcements",
      "quickAccess",
      "operationalActivity",
      "agentOnboarding",
      "complianceExceptions",
      "supportQueue",
      "teamTasks",
      "roomUtilization",
      "overdueInventory",
      "quickDocuments",
    ],
  },
  {
    id: "broker",
    label: "Broker",
    description:
      "Brokerage-wide production, compliance exposure, and the contracts still open.",
    roleCodes: ["principal_broker", "broker_admin"],
    priority: 1,
    widgets: [
      "performance",
      "announcements",
      "quickAccess",
      "closingPipeline",
      "complianceExceptions",
      "agentOnboarding",
      "operationalActivity",
      "contractsAwaitingSignature",
      "teamTasks",
      "myDay",
    ],
  },
  {
    id: "regional",
    label: "Regional leadership",
    description: "Production and staffing across every office in the region.",
    roleCodes: ["regional_manager", "regional_admin"],
    priority: 3,
    widgets: [
      "performance",
      "announcements",
      "quickAccess",
      "closingPipeline",
      "agentOnboarding",
      "operationalActivity",
      "teamTasks",
      "contractsAwaitingSignature",
      "roomUtilization",
      "myDay",
    ],
  },
  {
    id: "transactionCoordinator",
    label: "Transaction Coordinator",
    description: "Files in flight, what is waiting on a signature, and what is late.",
    roleCodes: ["regional_transaction_coordinator", "transaction_coordinator"],
    priority: 5,
    widgets: [
      "performance",
      "announcements",
      "quickAccess",
      "closingPipeline",
      "activeTransactions",
      "contractsAwaitingSignature",
      "teamTasks",
      "myDay",
      "quickDocuments",
    ],
  },
  {
    id: "branchManager",
    label: "Branch Manager",
    description: "The office's production, people, and obligations for today.",
    roleCodes: ["branch_manager"],
    priority: 6,
    widgets: [
      "performance",
      "announcements",
      "quickAccess",
      "closingPipeline",
      "agentOnboarding",
      "operationalActivity",
      "myDay",
      "teamTasks",
      "roomUtilization",
      "overdueInventory",
    ],
  },
  {
    id: "branchAdmin",
    label: "Office Admin",
    description: "Office operations: onboarding, rooms, inventory, and training.",
    roleCodes: ["branch_admin"],
    priority: 7,
    widgets: [
      "performance",
      "announcements",
      "quickAccess",
      "agentOnboarding",
      "training",
      "myDay",
      "teamTasks",
      "roomUtilization",
      "overdueInventory",
      "quickDocuments",
    ],
  },
  {
    id: "agent",
    label: "Agent",
    description: "Your book of business, today's schedule, and what needs doing.",
    roleCodes: ["realtor"],
    priority: 9,
    widgets: [
      "performance",
      "announcements",
      "quickAccess",
      "activeTransactions",
      "training",
      "myDay",
      "actionItems",
      "marketSnapshot",
      "quickDocuments",
    ],
  },
  {
    id: "marketing",
    label: "Marketing",
    description: "What is published, how it landed, and what agents are asking for.",
    roleCodes: ["marketing_team"],
    priority: 10,
    widgets: [
      "performance",
      "announcements",
      "quickAccess",
      "feedbackSignals",
      "training",
      "myDay",
      "quickDocuments",
    ],
  },
  {
    id: "accounting",
    label: "Accounting",
    description: "Closings coming due and the contracts behind them.",
    roleCodes: ["accountant"],
    priority: 11,
    widgets: [
      "performance",
      "announcements",
      "quickAccess",
      "closingPipeline",
      "operationalActivity",
      "contractsAwaitingSignature",
      "myDay",
      "quickDocuments",
    ],
  },
  {
    id: "compliance",
    label: "Compliance",
    description: "Exceptions to review, licences to chase, and contracts still open.",
    roleCodes: ["compliance"],
    priority: 12,
    widgets: [
      "performance",
      "announcements",
      "quickAccess",
      "complianceExceptions",
      "agentOnboarding",
      "operationalActivity",
      "contractsAwaitingSignature",
      "myDay",
      "quickDocuments",
    ],
  },
  {
    id: "itSupport",
    label: "IT Support",
    description: "The support queue, platform tasks, and account activity.",
    roleCodes: ["it_support"],
    priority: 13,
    widgets: [
      "performance",
      "announcements",
      "quickAccess",
      "supportQueue",
      "operationalActivity",
      "myDay",
      "teamTasks",
      "overdueInventory",
    ],
  },
  {
    id: "authenticated",
    label: "Standard",
    description: "The brokerage essentials, available to every signed-in colleague.",
    roleCodes: [],
    // Last by construction: the fallback must never win a priority comparison.
    priority: Number.MAX_SAFE_INTEGER,
    widgets: AUTHENTICATED_WIDGETS,
  },
] as const;

export const FALLBACK_PROFILE_ID: DashboardProfileId = "authenticated";

const BY_ID = new Map<string, DashboardProfile>(
  DASHBOARD_PROFILES.map((profile) => [profile.id, profile]),
);

/** Role code → profile. Built once; a role maps to at most one profile. */
const BY_ROLE_CODE = new Map<string, DashboardProfile>();
for (const profile of DASHBOARD_PROFILES) {
  for (const code of profile.roleCodes) {
    if (!BY_ROLE_CODE.has(code)) {
      BY_ROLE_CODE.set(code, profile);
    }
  }
}

export function getDashboardProfile(id: string): DashboardProfile | undefined {
  return BY_ID.get(id);
}

export function profileForRoleCode(code: string): DashboardProfile | undefined {
  return BY_ROLE_CODE.get(code);
}

export function fallbackProfile(): DashboardProfile {
  const profile = BY_ID.get(FALLBACK_PROFILE_ID);
  if (!profile) {
    throw new Error("The dashboard fallback profile is missing from the registry.");
  }
  return profile;
}
