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

export interface DashboardStat {
  value: string;
  hint: string;
  tone: "default" | "alert" | "warning" | "success";
}

export interface DashboardStats {
  activeTransactions: DashboardStat;
  upcomingClosings: DashboardStat;
  pendingTasks: DashboardStat;
  commissionYtd: DashboardStat;
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
 * Availability per hub section, keyed by the section slug used in the
 * `coming_soon` URL. Shared by web.navigation.HUB_FEATURES.
 */
export type HubFeatures = Record<string, boolean>;

export interface PageProps {
  user: User | null;
  csrfToken: string;
  requestId: string;
  features: HubFeatures;
  primaryOffice: PrimaryOffice | null;
  [key: string]: unknown;
}

/** Dashboard page props. Deferred widgets are undefined until Inertia loads them. */
export interface DashboardPageProps extends PageProps {
  stats?: DashboardStats;
  quickApps?: DashboardQuickApp[];
  announcements?: DashboardAnnouncements;
  transactions?: DashboardTransaction[];
  training?: DashboardTraining;
  schedule?: DashboardSchedule;
  actionItems?: DashboardActionItems;
  market?: DashboardMarket;
  documents?: DashboardDocument[];
}
