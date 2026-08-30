/**
 * Preview payloads for widgets whose provider has not shipped.
 *
 * Every administrative widget already reads its real `DashboardWidget<T>`
 * envelope from props. Until the provider behind it exists there is no
 * envelope to read, and a page of grey "not connected" panels cannot be
 * reviewed for layout, density, or copy. These fixtures fill that gap and are
 * labelled as preview data everywhere they render.
 *
 * The rules that keep this honest:
 *
 * - A preview is only consulted for a widget whose registry row says
 *   `backed: false`. A server envelope — including an empty or failed one —
 *   always wins.
 * - Every unbacked widget needs an entry. Without one its slot renders nothing
 *   at all, which is worse than a panel saying it has no data;
 *   `DashboardWidgetSlot.test.tsx` fails if one is missing.
 * - Registering a provider means flipping `backed` to `true` in the same
 *   commit, at which point the fixture below is dead and should be deleted.
 * - Nothing here is scoped, aggregated, or derived from a real record. It is
 *   illustrative shape, not data.
 */

// The one photograph in the bundle. Reused here so the news carousel can be
// reviewed with real artwork in it; it goes away with this whole file.
import previewPhoto from "@/images/loginpage.jpg";
import type { DashboardWidgetId } from "@/lib/dashboard/widget-registry";
import type {
  DashboardActivity,
  DashboardAnnouncements,
  DashboardMeter,
  DashboardQueue,
  DashboardScopeOption,
  DashboardStages,
  DashboardWidget,
} from "@/types";

/** Fixed so preview output is deterministic across renders and snapshots. */
const PREVIEW_GENERATED_AT = "2026-08-20T09:00:00-04:00";

function previewWidget<T>(data: T): DashboardWidget<T> {
  return {
    status: "ready",
    version: 0,
    generatedAt: PREVIEW_GENERATED_AT,
    data,
    emptyState: null,
    unavailable: null,
    meta: { preview: true },
  };
}

const announcements: DashboardAnnouncements = {
  featured: {
    id: 1,
    href: "/announcements/1",
    tag: "Policy",
    title: "Updated commission schedule takes effect 1 September",
    excerpt:
      "Splits and cap thresholds change for the new plan year. Read it before your next listing appointment.",
    imageUrl: previewPhoto,
  },
  // Deliberately mixed: some items carry artwork and some do not, because the
  // carousel has to hold its shape either way once editors are publishing.
  items: [
    {
      id: 2,
      href: "/announcements/2",
      tag: "Event",
      title: "Fall kickoff — 4 September, Fairfax VA",
      excerpt: "Doors at 9, awards at noon.",
      imageUrl: previewPhoto,
    },
    {
      id: 3,
      href: "/announcements/3",
      tag: "Training",
      title: "New contract forms: what changed and why",
      excerpt: "A 20-minute walkthrough of the revised purchase agreement.",
    },
    {
      id: 4,
      href: "/announcements/4",
      tag: "Operations",
      title: "Arlington office moves to the third floor this weekend",
      excerpt: "Pack your desk by Friday at 5.",
      imageUrl: previewPhoto,
    },
    {
      id: 5,
      href: "/announcements/5",
      tag: "People",
      title: "Welcome to the six agents who joined us this month",
      excerpt: "Say hello when you see them in the office.",
    },
  ],
};

const agentOnboarding: DashboardStages = {
  caption: "12 agents in onboarding",
  stages: [
    { key: "invited", label: "Invited", value: "3", tone: "neutral" },
    { key: "profile", label: "Profile in progress", value: "4", tone: "info" },
    {
      key: "licensing",
      label: "Licence review",
      value: "3",
      hint: "1 waiting over a week",
      tone: "warning",
    },
    { key: "ready", label: "Ready to activate", value: "2", tone: "success" },
  ],
};

const closingPipeline: DashboardStages = {
  caption: "48 files in flight",
  stages: [
    { key: "underContract", label: "Under contract", value: "18", tone: "neutral" },
    { key: "inspection", label: "Inspection & appraisal", value: "14", tone: "info" },
    {
      key: "clearToClose",
      label: "Clear to close",
      value: "6",
      hint: "4 close this week",
      tone: "success",
    },
    {
      key: "atRisk",
      label: "At risk",
      value: "10",
      hint: "Financing or contingency slipped",
      tone: "destructive",
    },
  ],
};

const contractsAwaitingSignature: DashboardQueue = {
  total: 7,
  rows: [
    {
      id: "ON-1048",
      title: "1428 Grove Avenue",
      subtitle: "Listing agreement · Avery Johnson",
      meta: "Sent 3 days ago",
      badge: "Awaiting seller",
      tone: "warning",
    },
    {
      id: "ON-1044",
      title: "88 Franklin Street",
      subtitle: "Buyer representation · Morgan Lee",
      meta: "Sent yesterday",
      badge: "Awaiting buyer",
      tone: "info",
    },
    {
      id: "ON-1039",
      title: "26 Kestrel Lane",
      subtitle: "Amendment · Taylor Bennett",
      meta: "Sent 9 days ago",
      badge: "Overdue",
      tone: "destructive",
    },
  ],
};

const complianceExceptions: DashboardQueue = {
  total: 5,
  rows: [
    {
      id: "exc-licence",
      title: "Licence expiring",
      subtitle: "2 agents · Fairfax VA",
      meta: "Within 30 days",
      badge: "Action needed",
      tone: "warning",
    },
    {
      id: "exc-missing-doc",
      title: "Missing disclosure",
      subtitle: "ON-1031 · 7 Bramble Court",
      meta: "Closed 4 days ago",
      badge: "Post-closing",
      tone: "destructive",
    },
    {
      id: "exc-ce",
      title: "Continuing education overdue",
      subtitle: "1 agent · Arlington VA",
      meta: "12 days late",
      badge: "Overdue",
      tone: "destructive",
    },
  ],
};

const teamTasks: DashboardQueue = {
  total: 9,
  rows: [
    {
      id: "task-welcome",
      title: "Welcome call — Jordan Ellis",
      subtitle: "Onboarding",
      meta: "Due today",
      tone: "info",
    },
    {
      id: "task-audit",
      title: "File audit — ON-1042",
      subtitle: "Compliance",
      meta: "Due tomorrow",
      tone: "neutral",
    },
    {
      id: "task-keys",
      title: "Collect lockbox keys",
      subtitle: "Office operations",
      meta: "2 days late",
      badge: "Late",
      tone: "destructive",
    },
  ],
};

const overdueInventory: DashboardQueue = {
  total: 4,
  rows: [
    {
      id: "inv-sign-12",
      title: "Yard signs (12)",
      subtitle: "Checked out by Priya Raman",
      meta: "6 days over",
      badge: "Overdue",
      tone: "destructive",
    },
    {
      id: "inv-lockbox",
      title: "Lockboxes (3)",
      subtitle: "Checked out by Chris Doyle",
      meta: "2 days over",
      badge: "Overdue",
      tone: "warning",
    },
  ],
};

const roomUtilization: DashboardMeter = {
  headline: "64%",
  caption: "Booked room-minutes over published open hours, last 7 days",
  series: [
    { label: "Conference room", ratio: 0.82, caption: "Booked 41 of 50 hours" },
    { label: "Training room", ratio: 0.55, caption: "Booked 22 of 40 hours" },
    { label: "Closing room", ratio: 0.36, caption: "Booked 9 of 25 hours" },
    { label: "Podcast studio", ratio: null, caption: "No published open hours" },
  ],
};

const operationalActivity: DashboardActivity = {
  entries: [
    {
      id: "act-1",
      actor: "Dana Whitfield",
      action: "activated",
      target: "Jordan Ellis",
      at: "09:12",
      tone: "success",
    },
    {
      id: "act-2",
      actor: "Sam Oyelaran",
      action: "reassigned office for",
      target: "Priya Raman",
      at: "08:47",
      tone: "info",
    },
    {
      id: "act-3",
      actor: "Compliance",
      action: "flagged",
      target: "ON-1031",
      at: "Yesterday",
      tone: "warning",
    },
    {
      id: "act-4",
      actor: "Dana Whitfield",
      action: "revoked Branch Admin from",
      target: "Chris Doyle",
      at: "Yesterday",
      tone: "destructive",
    },
  ],
};

const supportQueue: DashboardQueue = {
  total: 6,
  rows: [
    {
      id: "sup-401",
      title: "Cannot sign in after office move",
      subtitle: "Priya Raman · Arlington VA",
      meta: "Opened 2 hours ago",
      badge: "High",
      tone: "destructive",
    },
    {
      id: "sup-398",
      title: "Requesting contract signing access",
      subtitle: "Chris Doyle · Fairfax VA",
      meta: "Opened yesterday",
      badge: "Normal",
      tone: "info",
    },
    {
      id: "sup-392",
      title: "Headshot upload fails on mobile",
      subtitle: "Jordan Ellis · Fairfax VA",
      meta: "Opened 3 days ago",
      badge: "Low",
      tone: "neutral",
    },
  ],
};

const feedbackSignals: DashboardQueue = {
  total: 11,
  rows: [
    {
      id: "fb-listing-kit",
      title: "Listing kit templates",
      subtitle: "8 mentions this week",
      meta: "Mostly positive",
      badge: "Trending",
      tone: "success",
    },
    {
      id: "fb-social",
      title: "Social post scheduling",
      subtitle: "5 requests",
      meta: "Feature request",
      badge: "Requested",
      tone: "info",
    },
    {
      id: "fb-print",
      title: "Print order turnaround",
      subtitle: "3 complaints",
      meta: "Escalating",
      badge: "Needs reply",
      tone: "warning",
    },
  ],
};

/**
 * Preview envelopes, one per unbacked widget id and typed as that widget's own
 * payload, so a fixture that drifts from the contract fails `tsc` rather than
 * rendering something the real provider could never return.
 */
export interface PreviewWidgets {
  announcements: DashboardWidget<DashboardAnnouncements>;
  agentOnboarding: DashboardWidget<DashboardStages>;
  closingPipeline: DashboardWidget<DashboardStages>;
  contractsAwaitingSignature: DashboardWidget<DashboardQueue>;
  complianceExceptions: DashboardWidget<DashboardQueue>;
  teamTasks: DashboardWidget<DashboardQueue>;
  overdueInventory: DashboardWidget<DashboardQueue>;
  roomUtilization: DashboardWidget<DashboardMeter>;
  operationalActivity: DashboardWidget<DashboardActivity>;
  supportQueue: DashboardWidget<DashboardQueue>;
  feedbackSignals: DashboardWidget<DashboardQueue>;
}

export const PREVIEW_WIDGETS: PreviewWidgets = {
  announcements: previewWidget(announcements),
  agentOnboarding: previewWidget(agentOnboarding),
  closingPipeline: previewWidget(closingPipeline),
  contractsAwaitingSignature: previewWidget(contractsAwaitingSignature),
  complianceExceptions: previewWidget(complianceExceptions),
  teamTasks: previewWidget(teamTasks),
  overdueInventory: previewWidget(overdueInventory),
  roomUtilization: previewWidget(roomUtilization),
  operationalActivity: previewWidget(operationalActivity),
  supportQueue: previewWidget(supportQueue),
  feedbackSignals: previewWidget(feedbackSignals),
};

/** Widget ids a preview fixture exists for. */
export const PREVIEW_WIDGET_IDS: readonly DashboardWidgetId[] = Object.keys(
  PREVIEW_WIDGETS,
) as DashboardWidgetId[];

/**
 * Illustrative scope options, used only while the server sends no `scope`
 * prop. Selecting one cannot widen what a provider returns: the real selector
 * sends the key back and the server revalidates it against effective access.
 */
export const PREVIEW_SCOPE_OPTIONS: DashboardScopeOption[] = [
  { key: "preview-company", label: "Brokerage-wide", level: "company" },
  { key: "preview-region-northern-va", label: "Northern Virginia", level: "region" },
  { key: "preview-office-fairfax", label: "Fairfax VA", level: "office" },
];
