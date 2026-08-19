export interface User {
  id: number;
  email: string;
  name: string;
  /** Django auth permission codenames, e.g. "user.view_user". */
  permissions: string[];
  /** Role (Django group) names, highest-priority first. */
  roles: string[];
  /** Display label: Superadmin, Admin, Region manager, Branch manager, Agent. */
  roleLabel: string;
  isStaff: boolean;
  isSuperuser: boolean;
}

/**
 * Dashboard metrics, selected and calculated server-side by
 * `apps/web/metrics.py`. The page renders whatever arrives: which cards a user
 * gets is a permission and scope decision the client is never asked to make.
 */
export type MetricScopeLevel = "self" | "office" | "region" | "company";

export interface DashboardMetric {
  key: string;
  label: string;
  /** Presentation hint for the figure; the value arrives already formatted. */
  format: "count" | "currency" | "percent";
  scopeLevel: MetricScopeLevel;
  /** How the figure is calculated — surfaced as the card's tooltip. */
  definition: string;
  availability: "available" | "unavailable";
  /** Why the figure cannot be shown; present only when unavailable. */
  unavailableReason?: string;
  /** Null while unavailable — an unmeasured metric has no number to round. */
  value: string | null;
  hint: string;
  tone: "neutral" | "success" | "warning" | "destructive";
  trend: "up" | "down" | "flat";
  /** Server-reversed destination, already guarded by its own permission. */
  drillDown: { href: string; label: string } | null;
}

export interface DashboardMetricGroup {
  key: string;
  title: string;
  description: string;
  metrics: DashboardMetric[];
}

export interface DashboardMetrics {
  /** What the team figures cover, e.g. "Fairfax VA" or "Brokerage-wide". */
  scope: { level: MetricScopeLevel; label: string };
  groups: DashboardMetricGroup[];
}

export interface DashboardQuickApp {
  id: string;
  name: string;
  href: string;
}

export interface DashboardAnnouncement {
  tag: string;
  title: string;
  excerpt: string;
  imageUrl?: string;
}

export interface DashboardAnnouncements {
  featured: DashboardAnnouncement;
  items: DashboardAnnouncement[];
}

export interface DashboardTransaction {
  id: string;
  address: string;
  imageUrl: string;
  type: string;
  stage: string;
  closing: string;
  /** Raw backend code; rendered only through an explicit presentation adapter. */
  status: string;
}

export interface DashboardTraining {
  percent: number;
  label: string;
  resourceTitle: string;
  resourceHint: string;
}

export interface DashboardScheduleEvent {
  time: string;
  title: string;
  place: string;
}

export interface DashboardSchedule {
  dateLabel: string;
  events: DashboardScheduleEvent[];
}

export interface DashboardActionItem {
  id: string;
  title: string;
  property: string;
  due: string;
  late: boolean;
}

export interface DashboardActionItems {
  total: number;
  items: DashboardActionItem[];
}

export interface DashboardMarketRate {
  label: string;
  value: string;
  bar: number;
}

export interface DashboardMarket {
  rates: DashboardMarketRate[];
}

export interface DashboardDocument {
  id: string;
  name: string;
}

export interface DashboardGreeting {
  salutation: string;
  name: string;
  dateLabel: string;
  /** Local calendar date in ISO 8601 form. */
  dateIso: string;
  timezone: string;
}

export interface DashboardWidgetEmptyState {
  title: string;
  description: string;
  actionLabel?: string;
  /** Server-reversed destination for the next useful action. */
  actionHref?: string;
}

export interface DashboardWidgetUnavailable {
  reason: string;
  retryable: boolean;
  actionLabel?: string;
  /** Server-reversed destination for a module that is not connected yet. */
  actionHref?: string;
}

interface DashboardWidgetBase {
  /** Bumped when this widget's data shape changes. */
  version: number;
  generatedAt: string;
  meta: { truncated?: boolean; [key: string]: unknown };
}

export type DashboardWidget<T> = DashboardWidgetBase &
  (
    | {
        status: "ready";
        data: T;
        emptyState: null;
        unavailable: null;
      }
    | {
        status: "empty";
        data: null;
        emptyState: DashboardWidgetEmptyState;
        unavailable: null;
      }
    | {
        status: "unavailable";
        data: null;
        emptyState: null;
        unavailable: DashboardWidgetUnavailable;
      }
  );

export type DashboardWidgetProp =
  | "metrics"
  | "quickApps"
  | "announcements"
  | "transactions"
  | "training"
  | "schedule"
  | "actionItems"
  | "market"
  | "documents";

/**
 * Props available on every Inertia page. `user` and `csrfToken` are shared by
 * `web.middleware.InertiaShareMiddleware`; pages can extend this interface.
 */
/** The signed-in user's own office. Never addressed by an id from the client. */
export interface PrimaryOffice {
  id: number;
  name: string;
  regionName: string;
}

/**
 * Availability per agent or administrative module, keyed by the stable item
 * slug in the shared navigation registries. Shared by web.navigation.HUB_FEATURES.
 */
export type HubFeatures = Record<string, boolean>;

export interface ShellSharedProps {
  /** Changes whenever roles, permissions, or authorization scope changes. */
  authorizationVersion: string;
  help: {
    /** Backend-validated HTTPS destination; null keeps the entry point disabled. */
    url: string | null;
  };
  session: {
    authenticated: boolean;
  };
}

export interface PageProps {
  user: User | null;
  csrfToken: string;
  requestId: string;
  features: HubFeatures;
  primaryOffice: PrimaryOffice | null;
  shell: ShellSharedProps;
  [key: string]: unknown;
}

/** Dashboard page props. Deferred widgets are undefined until Inertia loads them. */
export interface DashboardPageProps extends PageProps {
  greeting: DashboardGreeting;
  metrics?: DashboardWidget<DashboardMetrics>;
  quickApps?: DashboardWidget<DashboardQuickApp[]>;
  announcements?: DashboardWidget<DashboardAnnouncements>;
  transactions?: DashboardWidget<DashboardTransaction[]>;
  training?: DashboardWidget<DashboardTraining>;
  schedule?: DashboardWidget<DashboardSchedule>;
  actionItems?: DashboardWidget<DashboardActionItems>;
  market?: DashboardWidget<DashboardMarket>;
  documents?: DashboardWidget<DashboardDocument[]>;
}
