/**
 * Brokerage role catalog for presentation only.
 *
 * Authorization must use Django permission codenames (`user.permissions`),
 * never a visible role badge or label. Codes stay stable when display names
 * change.
 */

export type RoleScopeType = "company" | "region" | "office" | "assigned_record";

export interface RoleCatalogEntry {
  code: string;
  label: string;
  description: string;
  validScopeTypes: RoleScopeType[];
  protected: boolean;
}

export const ROLE_CATALOG: readonly RoleCatalogEntry[] = [
  {
    code: "system_admin",
    label: "System Admin",
    description:
      "Platform and brokerage-wide administration. May configure roles, offices, and operational modules company-wide.",
    validScopeTypes: ["company"],
    protected: true,
  },
  {
    code: "principal_broker",
    label: "Principal Broker",
    description:
      "Licensed principal with brokerage-wide authority. Protected; assignment requires enhanced audit.",
    validScopeTypes: ["company"],
    protected: true,
  },
  {
    code: "broker_admin",
    label: "Broker Admin",
    description:
      "Brokerage operations administrator. May assign non-protected roles within company scope.",
    validScopeTypes: ["company"],
    protected: false,
  },
  {
    code: "regional_manager",
    label: "Regional Manager",
    description:
      "Owns performance and staffing for a region and its descendant offices.",
    validScopeTypes: ["region"],
    protected: false,
  },
  {
    code: "regional_admin",
    label: "Regional Admin",
    description:
      "Supports regional operations and people administration without full regional-manager authority.",
    validScopeTypes: ["region"],
    protected: false,
  },
  {
    code: "regional_transaction_coordinator",
    label: "Regional Transaction Coordinator",
    description: "Coordinates transactions across offices in a region.",
    validScopeTypes: ["region", "assigned_record"],
    protected: false,
  },
  {
    code: "branch_manager",
    label: "Branch Manager",
    description: "Owns a branch or regional office.",
    validScopeTypes: ["office"],
    protected: false,
  },
  {
    code: "branch_admin",
    label: "Branch Admin / Office Admin",
    description:
      "Office operations support: people lists, training, and documents within a single office.",
    validScopeTypes: ["office"],
    protected: false,
  },
  {
    code: "transaction_coordinator",
    label: "Transaction Coordinator",
    description: "Runs transaction files for an office.",
    validScopeTypes: ["office", "assigned_record"],
    protected: false,
  },
  {
    code: "realtor",
    label: "Realtor",
    description: "Licensed agent. Default role for new signups.",
    validScopeTypes: ["office", "assigned_record"],
    protected: false,
  },
  {
    code: "marketing_team",
    label: "Marketing Team",
    description: "Brokerage marketing: announcements and feedback company-wide.",
    validScopeTypes: ["company"],
    protected: false,
  },
  {
    code: "accountant",
    label: "Accountant",
    description:
      "Financial operations: transaction and people visibility for reconciliation.",
    validScopeTypes: ["company"],
    protected: false,
  },
  {
    code: "compliance",
    label: "Compliance",
    description: "Compliance review of licenses, contracts, and related documents.",
    validScopeTypes: ["company"],
    protected: false,
  },
  {
    code: "it_support",
    label: "IT Support",
    description: "IT support queues and sanitized platform task visibility.",
    validScopeTypes: ["company"],
    protected: false,
  },
] as const;

const BY_CODE = new Map(ROLE_CATALOG.map((entry) => [entry.code, entry]));

export function getRoleCatalogEntry(code: string): RoleCatalogEntry | undefined {
  return BY_CODE.get(code);
}

export function roleLabel(code: string): string {
  return BY_CODE.get(code)?.label ?? code;
}

export function roleDescription(code: string): string {
  return BY_CODE.get(code)?.description ?? "";
}

export function protectedRoleBlockReason(code: string): string | null {
  const entry = BY_CODE.get(code);
  if (!entry?.protected) {
    return null;
  }
  return `${entry.label} is a protected system role. Only a superadmin can assign it, and the change is heavily audited.`;
}
