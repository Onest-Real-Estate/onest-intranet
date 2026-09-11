/**
 * The allowlist of dashboard widgets.
 *
 * A dashboard profile is a list of ids from this registry and nothing else. It
 * never carries a component name, an import path, a query, or any other
 * expression a reader or an administrator could author — a profile that names
 * an id not registered here resolves to no widget at all.
 *
 * Rendering a widget is not authorization. `permissions` decides whether the
 * *card* is laid out; the provider behind `prop` applies the same permissions
 * and the reader's effective scope server-side, and every `href` a widget
 * offers is guarded by its own policy.
 */

import type { PermissionCheck } from "@/lib/permissions";
import type { DashboardWidgetProp, MetricScopeLevel } from "@/types";

export type DashboardWidgetId =
  | "performance"
  | "quickAccess"
  | "myDay"
  | "actionItems"
  | "activeTransactions"
  | "announcements"
  | "training"
  | "marketSnapshot"
  | "quickDocuments"
  | "agentOnboarding"
  | "closingPipeline"
  | "contractsAwaitingSignature"
  | "complianceExceptions"
  | "teamTasks"
  | "overdueInventory"
  | "roomUtilization"
  | "operationalActivity"
  | "supportQueue"
  | "feedbackSignals";

/**
 * How wide a widget needs to be to stay legible.
 *
 * `wide` owns a whole row, `main` is a reading-width panel, `rail` is a narrow
 * one for today's obligations. These are widths, not containers: there is one
 * twelve-column grid, and `lib/dashboard/layout.ts` packs widgets into rows
 * from these values. A profile orders widgets; the registry sizes them.
 */
export type DashboardWidgetColumn = "wide" | "main" | "rail";

/**
 * What to do when the reader does not hold the widget's permissions.
 *
 * `omit` drops the card silently — the normal answer, because a dashboard full
 * of locked panels is noise. `withhold` renders a restricted placeholder, and
 * is reserved for widgets whose absence would misdescribe the page: a
 * compliance dashboard with no compliance panel reads as "nothing to review".
 * Mirrors `unavailable_behavior` in the backend metric registry.
 */
export type DashboardDeniedBehavior = "omit" | "withhold";

export interface DashboardWidgetDefinition {
  id: DashboardWidgetId;
  title: string;
  /** Inertia prop carrying this widget's envelope, and its reload target. */
  prop: DashboardWidgetProp;
  /**
   * True once a server provider fills `prop`. False means the card renders as
   * *not connected* — never as an invented figure; flip the flag in the same
   * commit that registers the provider and the panel starts reading real data.
   */
  backed: boolean;
  /** Every listed permission is required before the card is laid out. */
  permissions: PermissionCheck;
  deniedBehavior: DashboardDeniedBehavior;
  column: DashboardWidgetColumn;
  /**
   * Columns out of twelve this widget occupies, overriding the width `column`
   * implies, so two widgets can share a row that neither would otherwise fill.
   * Only honored once there is a twelve-column grid to divide — everything
   * stacks below `xl`.
   */
  span?: number;
  /**
   * Breadths the widget is meaningful at. A widget offered to a scope it is
   * not defined for would relabel an office figure as a company one.
   */
  scopes: readonly MetricScopeLevel[];
}

const ALL_SCOPES: readonly MetricScopeLevel[] = ["self", "office", "region", "company"];
const TEAM_SCOPES: readonly MetricScopeLevel[] = ["office", "region", "company"];

/**
 * Registry order is layout-independent but stable: it is the tie-break used
 * when two profiles are compared and the order tests assert against.
 */
export const DASHBOARD_WIDGETS: readonly DashboardWidgetDefinition[] = [
  {
    id: "performance",
    title: "Performance",
    prop: "metrics",
    backed: true,
    // The metric registry decides card by card what this reader may see, so
    // the panel itself asks for nothing.
    permissions: {},
    deniedBehavior: "omit",
    column: "wide",
    scopes: ALL_SCOPES,
  },
  {
    id: "quickAccess",
    title: "Quick access",
    prop: "quickApps",
    backed: true,
    permissions: {},
    deniedBehavior: "omit",
    column: "wide",
    span: 4,
    scopes: ALL_SCOPES,
  },
  {
    id: "myDay",
    title: "My day",
    prop: "schedule",
    backed: true,
    permissions: {},
    deniedBehavior: "omit",
    column: "rail",
    scopes: ALL_SCOPES,
  },
  {
    id: "actionItems",
    title: "Action items",
    prop: "actionItems",
    backed: true,
    permissions: { any: ["web.view_own_tasks"] },
    deniedBehavior: "omit",
    column: "rail",
    scopes: ALL_SCOPES,
  },
  {
    id: "activeTransactions",
    title: "Active transactions",
    prop: "transactions",
    backed: true,
    permissions: { any: ["web.view_own_transactions", "web.view_transactions"] },
    deniedBehavior: "omit",
    column: "main",
    scopes: ALL_SCOPES,
  },
  {
    id: "announcements",
    title: "News & announcements",
    prop: "announcements",
    // Backed by `providers.announcements`, which reads the same audience
    // predicate as the announcements feed. The flag matters twice: it is what
    // makes the panel wait behind `<Deferred>` for its own skeleton instead of
    // rendering not-connected, and what stops the page listing the band as an
    // unbuilt module for the one frame before the prop lands.
    backed: true,
    permissions: {},
    deniedBehavior: "omit",
    // Top of the page in every profile: brokerage news is the one thing
    // everybody is meant to have read, and a panel two columns down in a rail
    // is a panel nobody reads. It shares that row with the launchers rather
    // than spending a full band on one story.
    column: "wide",
    span: 8,
    scopes: ALL_SCOPES,
  },
  {
    id: "training",
    title: "Training & resources",
    prop: "training",
    backed: true,
    permissions: {},
    deniedBehavior: "omit",
    column: "main",
    scopes: ALL_SCOPES,
  },
  {
    id: "marketSnapshot",
    title: "Market snapshot",
    prop: "market",
    backed: true,
    permissions: {},
    deniedBehavior: "omit",
    column: "rail",
    scopes: ALL_SCOPES,
  },
  {
    id: "quickDocuments",
    title: "Quick documents",
    prop: "documents",
    backed: true,
    permissions: {},
    deniedBehavior: "omit",
    column: "rail",
    scopes: ALL_SCOPES,
  },
  {
    id: "agentOnboarding",
    title: "Agent onboarding",
    prop: "agentOnboarding",
    backed: true,
    permissions: {
      any: ["web.view_new_agents", "web.manage_new_agent_onboarding"],
    },
    deniedBehavior: "omit",
    column: "main",
    scopes: TEAM_SCOPES,
  },
  {
    id: "closingPipeline",
    title: "Closing pipeline",
    prop: "closingPipeline",
    backed: false,
    permissions: { all: ["web.view_transactions"] },
    deniedBehavior: "withhold",
    column: "main",
    scopes: TEAM_SCOPES,
  },
  {
    id: "contractsAwaitingSignature",
    title: "Awaiting signature",
    prop: "contractsAwaitingSignature",
    backed: true,
    permissions: { all: ["web.view_agent_contracts"] },
    deniedBehavior: "withhold",
    column: "rail",
    scopes: ALL_SCOPES,
  },
  {
    id: "complianceExceptions",
    title: "Compliance exceptions",
    prop: "complianceExceptions",
    backed: false,
    permissions: { all: ["web.view_compliance"] },
    deniedBehavior: "withhold",
    column: "main",
    scopes: TEAM_SCOPES,
  },
  {
    id: "teamTasks",
    title: "Team tasks",
    prop: "teamTasks",
    backed: true,
    // The grant the operational-tasks page itself enforces. It used to ask for
    // `view_office_tasks` or `view_platform_tasks`: the first is the metric
    // grant and the second is sanitized Celery job status, so a reader admitted
    // by either would have had every row link into a 403.
    permissions: { all: ["web.view_operational_tasks"] },
    deniedBehavior: "omit",
    column: "rail",
    scopes: TEAM_SCOPES,
  },
  {
    id: "overdueInventory",
    title: "Overdue inventory",
    prop: "overdueInventory",
    backed: true,
    permissions: { all: ["web.view_inventory"] },
    deniedBehavior: "omit",
    column: "rail",
    scopes: TEAM_SCOPES,
  },
  {
    id: "roomUtilization",
    title: "Room utilization",
    prop: "roomUtilization",
    backed: true,
    permissions: { all: ["web.view_reservations"] },
    deniedBehavior: "omit",
    column: "rail",
    scopes: TEAM_SCOPES,
  },
  {
    id: "operationalActivity",
    title: "Operational activity",
    prop: "operationalActivity",
    backed: false,
    permissions: { any: ["user.view_user_administration", "web.view_users"] },
    deniedBehavior: "omit",
    column: "main",
    scopes: TEAM_SCOPES,
  },
  {
    id: "supportQueue",
    title: "Support queue",
    prop: "supportQueue",
    backed: true,
    // The grant the IT queue destination enforces. `view_platform_tasks` is a
    // different module (sanitized Celery status) and never admitted anyone to
    // a support ticket.
    permissions: { all: ["web.view_it_support"] },
    deniedBehavior: "withhold",
    column: "main",
    scopes: TEAM_SCOPES,
  },
  {
    id: "feedbackSignals",
    title: "Feedback signals",
    prop: "feedbackSignals",
    backed: true,
    permissions: { all: ["web.view_feedback"] },
    deniedBehavior: "omit",
    column: "main",
    scopes: TEAM_SCOPES,
  },
] as const;

const BY_ID = new Map<DashboardWidgetId, DashboardWidgetDefinition>(
  DASHBOARD_WIDGETS.map((widget) => [widget.id, widget]),
);

export function getDashboardWidget(
  id: DashboardWidgetId,
): DashboardWidgetDefinition | undefined {
  return BY_ID.get(id);
}

/** Registry position, used as the deterministic tie-break in resolution. */
export function dashboardWidgetOrder(id: DashboardWidgetId): number {
  return DASHBOARD_WIDGETS.findIndex((widget) => widget.id === id);
}
