import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  AlertTriangle,
  BadgeCheck,
  Check,
  Download,
  ExternalLink,
  FileText,
  FileWarning,
  Loader2,
  type LucideIcon,
  PenLine,
  RefreshCw,
} from "lucide-react";
import { useId, useState } from "react";

import {
  Callout,
  EmptyState,
  MetricCard,
  MetricStrip,
  PageHeader,
  PanelHeader,
  ReadOnlyValue,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
  Timeline,
  type TimelineItem,
  toStatusTone,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type {
  MyContractDetail,
  MyContractHistoryRow,
  MyContractPageProps,
  MyContractState,
} from "@/types";
import type { StatusTone } from "@/types/design-system";

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const day = iso.slice(0, 10);
  return day || iso;
}

function formatStamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function displayValue(value: string | null | undefined): string {
  if (value == null || value === "") return "—";
  return value;
}

function PdfPreview({ contract }: { contract: MyContractDetail }) {
  const titleId = useId();
  const [embedFailed, setEmbedFailed] = useState(false);
  const previewKey = contract.previewUrl ?? "";

  if (!contract.previewUrl && !contract.downloadUrl) {
    return (
      <p className="text-muted-foreground text-sm">
        No PDF is available for this version yet.
      </p>
    );
  }

  const downloadHref = contract.downloadUrl ?? contract.previewUrl ?? "#";
  const previewHref = contract.previewUrl ?? contract.downloadUrl ?? "#";

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" asChild>
          <a href={downloadHref} download>
            <Download className="size-3.5" aria-hidden />
            Download PDF
          </a>
        </Button>
        <Button type="button" variant="ghost" size="sm" asChild>
          <a href={previewHref} target="_blank" rel="noopener noreferrer">
            <ExternalLink className="size-3.5" aria-hidden />
            Open in new tab
          </a>
        </Button>
      </div>

      {contract.previewUrl && !embedFailed ? (
        <section
          key={previewKey}
          className="border-border bg-muted/30 relative min-h-[28rem] overflow-hidden rounded-lg border"
          aria-labelledby={titleId}
        >
          <h3 id={titleId} className="sr-only">
            Agreement PDF preview
          </h3>
          <object
            data={`${contract.previewUrl}#view=FitH`}
            type="application/pdf"
            className="h-[min(70vh,40rem)] w-full"
            aria-label="Agreement PDF"
            onError={() => setEmbedFailed(true)}
          >
            <div className="grid gap-3 p-6">
              <p className="text-muted-foreground text-sm">
                Embedded preview is not supported in this browser. Download the PDF or
                open it in a new tab.
              </p>
              <Button type="button" variant="outline" size="sm" asChild>
                <a href={downloadHref} download>
                  <Download className="size-3.5" aria-hidden />
                  Download PDF
                </a>
              </Button>
            </div>
          </object>
        </section>
      ) : (
        <div className="border-border grid gap-3 rounded-lg border border-dashed p-6">
          <p className="text-muted-foreground text-sm">
            {embedFailed
              ? "Embedded preview could not load. Use download or open in a new tab."
              : "Preview is available as a download on this device."}
          </p>
          <Button type="button" variant="outline" size="sm" asChild>
            <a href={downloadHref} download>
              <Download className="size-3.5" aria-hidden />
              Download PDF
            </a>
          </Button>
        </div>
      )}
    </div>
  );
}

function CommissionSummary({ contract }: { contract: MyContractDetail }) {
  // Generated, not hardcoded: two of these on one page would otherwise share
  // an id and each `aria-labelledby` would resolve to whichever came first.
  const mentorId = useId();
  const referralId = useId();
  const commission = contract.commission;
  if (!commission) {
    return (
      <p className="text-muted-foreground text-sm">
        Commission terms are not available for your account.
      </p>
    );
  }

  const mentor = commission.mentor;
  const referral = commission.referral;
  const mentorSet =
    mentor.percent || mentor.fixedAmount || mentor.capAmount || mentor.basis;
  const referralSet =
    referral.percent || referral.fixedAmount || referral.capAmount || referral.basis;

  return (
    <div className="grid gap-6">
      {contract.summaryLines && contract.summaryLines.length > 0 ? (
        <ul className="text-foreground grid list-disc gap-1 pl-5 text-sm">
          {contract.summaryLines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}

      {/* These four are the terms an agent actually opens this page for, and
          they are figures. Rendered as label-and-value pairs they read as a
          form; on one ruled strip they share a baseline and can be compared at
          a glance — the split against the split, the fee against the cap. */}
      <MetricStrip min="11rem">
        <MetricCard
          label="Agent split"
          value={`${displayValue(commission.agentSplitPercent)}${
            commission.agentSplitPercent ? "%" : ""
          }`}
        />
        <MetricCard
          label="Office split"
          value={`${displayValue(commission.officeSplitPercent)}${
            commission.officeSplitPercent ? "%" : ""
          }`}
        />
        <MetricCard
          label="Transaction fee"
          value={
            [
              commission.transactionFeeAmount
                ? `$${commission.transactionFeeAmount}`
                : null,
              commission.transactionFeePercent
                ? `${commission.transactionFeePercent}%`
                : null,
            ]
              .filter(Boolean)
              .join(" · ") || "—"
          }
        />
        <MetricCard
          label="Annual cap"
          value={commission.annualCapAmount ? `$${commission.annualCapAmount}` : "—"}
        />
      </MetricStrip>

      {/*
        One ruled block split down the middle, not two bordered boxes inside a
        card. A card nested in a card gives the eye two edges to compare and
        says the inner thing is a separate object; mentor and referral are two
        halves of the same set of terms.
      */}
      <div className="border-border/60 grid overflow-hidden rounded-lg border md:grid-cols-2">
        <section
          aria-labelledby={mentorId}
          className="border-border/60 grid gap-2 border-b p-4 md:border-r md:border-b-0"
        >
          <h3 id={mentorId} className="text-sm font-semibold">
            Mentor
          </h3>
          {mentorSet ? (
            <dl className="grid gap-2 text-sm">
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">Percent</dt>
                <dd>{displayValue(mentor.percent)}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">Fixed</dt>
                <dd>{displayValue(mentor.fixedAmount)}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">Cap</dt>
                <dd>{displayValue(mentor.capAmount)}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">Basis</dt>
                <dd className="text-right">{displayValue(mentor.basis)}</dd>
              </div>
              {mentor.notes ? (
                <p className="text-muted-foreground mt-1 text-xs whitespace-pre-line">
                  {mentor.notes}
                </p>
              ) : null}
            </dl>
          ) : (
            <p className="text-muted-foreground text-sm">No mentor terms.</p>
          )}
        </section>

        <section aria-labelledby={referralId} className="grid gap-2 p-4">
          <h3 id={referralId} className="text-sm font-semibold">
            Referral
          </h3>
          {referralSet ? (
            <dl className="grid gap-2 text-sm">
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">Percent</dt>
                <dd>{displayValue(referral.percent)}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">Fixed</dt>
                <dd>{displayValue(referral.fixedAmount)}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">Cap</dt>
                <dd>{displayValue(referral.capAmount)}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">Basis</dt>
                <dd className="text-right">{displayValue(referral.basis)}</dd>
              </div>
              {referral.notes ? (
                <p className="text-muted-foreground mt-1 text-xs whitespace-pre-line">
                  {referral.notes}
                </p>
              ) : null}
            </dl>
          ) : (
            <p className="text-muted-foreground text-sm">No referral terms.</p>
          )}
        </section>
      </div>

      {contract.specialArrangements ? (
        <div className="grid gap-1">
          <h3 className="text-sm font-semibold">Special arrangements</h3>
          <p className="text-muted-foreground text-sm whitespace-pre-line">
            {contract.specialArrangements}
          </p>
        </div>
      ) : null}

      {contract.addendaReferences && contract.addendaReferences.length > 0 ? (
        <div className="grid gap-1">
          <h3 className="text-sm font-semibold">Addenda</h3>
          <ul className="text-muted-foreground list-disc pl-5 text-sm">
            {contract.addendaReferences.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function HistoryList({ rows }: { rows: MyContractHistoryRow[] }) {
  if (rows.length <= 1) {
    return (
      <p className="text-muted-foreground text-sm">
        No earlier versions or amendments to show.
      </p>
    );
  }

  return (
    <ul className="grid gap-2">
      {rows.map((row) => {
        const kindLabel = row.changeKindLabel || "Agreement";
        const relation =
          row.governing === "current"
            ? "Currently governing"
            : row.amendsPublicId
              ? "Amendment of an earlier version"
              : row.supersedesPublicId
                ? "Replacement of an earlier version"
                : row.statusLabel;
        const title = `Version ${row.versionNumber} · ${kindLabel}`;
        if (row.isFocus) {
          return (
            <li key={row.publicId}>
              <div className="border-border bg-muted/40 flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3">
                <div className="grid min-w-0 gap-0.5">
                  <span className="text-sm font-medium">{title}</span>
                  <span className="text-muted-foreground text-xs">
                    Effective {formatDate(row.effectiveOn)}
                    {row.expiresOn ? ` · Expires ${formatDate(row.expiresOn)}` : ""}
                    {` · ${relation}`}
                  </span>
                </div>
                <Badge variant="secondary">Current view</Badge>
              </div>
            </li>
          );
        }
        return (
          <li key={row.publicId}>
            <Link
              href={row.href}
              className="border-border hover:bg-muted/30 focus-visible:ring-ring flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 transition-colors focus-visible:ring-2 focus-visible:outline-none"
              preserveScroll
            >
              <div className="grid min-w-0 gap-0.5">
                <span className="text-sm font-medium">{title}</span>
                <span className="text-muted-foreground text-xs">
                  Effective {formatDate(row.effectiveOn)} · {relation}
                </span>
              </div>
              <StatusBadge
                status={{
                  label: row.statusLabel,
                  tone: toStatusTone(row.statusTone),
                }}
              />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function SignAction({
  canSign,
  signingReady,
}: {
  canSign: boolean;
  signingReady: boolean;
}) {
  if (!canSign) return null;

  if (signingReady) {
    return (
      <Button type="button" asChild>
        <Link href={routes.my_contract_sign()}>
          <PenLine className="size-3.5" aria-hidden />
          Sign contract
        </Link>
      </Button>
    );
  }

  // The reason lives on the page, not in a tooltip on a button nobody can
  // press. A tooltip on a disabled control is unreachable by touch and by
  // keyboard, so the one explanation for why the page will not do the thing it
  // is asking for was the hardest text on it to obtain.
  return (
    <Callout tone="warning" title="Signing is temporarily unavailable">
      You can still review and download the agreement below. Try again shortly.
    </Callout>
  );
}

/** The mark beside the next action, and how loudly the card carries it. */
const STATE_PRESENTATION: Record<
  MyContractState,
  { icon: LucideIcon; tone: StatusTone; spin?: boolean }
> = {
  no_contract: { icon: FileText, tone: "neutral" },
  generating: { icon: Loader2, tone: "info", spin: true },
  generation_failed: { icon: FileWarning, tone: "destructive" },
  awaiting_signature: { icon: PenLine, tone: "warning" },
  signed: { icon: Check, tone: "info" },
  active: { icon: BadgeCheck, tone: "success" },
  expired: { icon: AlertTriangle, tone: "warning" },
  superseded: { icon: FileText, tone: "neutral" },
  terminated: { icon: AlertTriangle, tone: "destructive" },
};

const MARK_TONE: Record<StatusTone, string> = {
  neutral: "bg-chip-neutral text-muted-foreground",
  info: "bg-chip-info text-info",
  success: "bg-chip-success text-success",
  warning: "bg-chip-warning text-warning-ink",
  destructive: "bg-chip-destructive text-destructive",
};

/**
 * How far the agreement has travelled, in the agent's own terms.
 *
 * Deliberately not the admin pipeline: `draft` and `ready_for_review` are
 * brokerage-internal words for a period when this agreement was not yet the
 * agent's business, and the four steps below are the ones they can actually
 * act on or wait for.
 */
function progressItems(contract: MyContractDetail): TimelineItem[] {
  const stages: Array<{ id: string; title: string; at: string | null }> = [
    { id: "sent", title: "Sent to you", at: contract.sentAt },
    { id: "viewed", title: "Opened", at: contract.viewedAt },
    { id: "signed", title: "Signed", at: contract.signedAt },
    { id: "active", title: "Active", at: contract.activatedAt },
  ];
  const ended =
    (contract.terminatedAt && { title: "Terminated", tone: "destructive" as const }) ||
    (contract.expiredAt && { title: "Expired", tone: "warning" as const }) ||
    (contract.supersededAt && { title: "Replaced", tone: "neutral" as const }) ||
    null;

  const reached = stages.reduce(
    (furthest, stage, index) => (stage.at ? index : furthest),
    -1,
  );
  const walked = ended ? reached + 1 : stages.length;

  const items: TimelineItem[] = stages.slice(0, walked).map((stage, index) => ({
    id: stage.id,
    title: stage.title,
    meta: stage.at ? formatStamp(stage.at) : undefined,
    tone: index < reached || ended ? "success" : index === reached ? "info" : "neutral",
    current: !ended && index === reached,
    icon: index < reached || (ended && index <= reached) ? Check : undefined,
  }));

  if (ended) {
    items.push({
      id: "ended",
      title: ended.title,
      meta: formatStamp(
        contract.terminatedAt ?? contract.expiredAt ?? contract.supersededAt,
      ),
      tone: ended.tone,
      current: true,
    });
  }
  return items;
}

/**
 * Self-service My Contract: status, plain-language terms, secure PDF, history.
 */
export default function MyContract() {
  const { state, nextAction, contract, history, capabilities, disclaimer, empty } =
    usePage<MyContractPageProps>().props;

  const presentation = STATE_PRESENTATION[state] ?? STATE_PRESENTATION.no_contract;
  const Icon = presentation.icon;

  function refresh() {
    router.get(routes.my_contract(), {}, { preserveScroll: true, replace: true });
  }

  return (
    <div className="grid gap-8">
      <Head title="My contract" />
      <PageHeader
        title="My contract"
        description="Your current brokerage agreement, terms summary, and document history."
        meta={
          contract ? (
            <StatusBadge
              status={{
                label: contract.statusLabel,
                tone: toStatusTone(contract.statusTone),
              }}
            />
          ) : null
        }
      />

      {empty || !contract ? null : (
        /*
          The one thing to do next, and its mark carries the state. The icon was
          previously always muted grey, so a failed PDF generation and a healthy
          active agreement announced themselves identically — the words were the
          only difference between "nothing to do" and "something is wrong".
        */
        <SurfaceCard>
          <SurfaceCardContent className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-start gap-3.5">
              <span
                className={cn(
                  "grid size-10 shrink-0 place-items-center rounded-md",
                  MARK_TONE[presentation.tone],
                )}
              >
                <Icon
                  className={cn("size-5", presentation.spin && "animate-spin")}
                  aria-hidden
                />
              </span>
              <div className="grid gap-1">
                <h2 className="text-base leading-6 font-semibold">
                  {nextAction.title}
                </h2>
                <p className="text-muted-foreground max-w-measure text-sm leading-5">
                  {nextAction.description}
                </p>
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              {nextAction.ctaKind === "sign" ? (
                <SignAction
                  canSign={capabilities.canSign}
                  signingReady={capabilities.signingReady}
                />
              ) : null}
              {nextAction.ctaKind === "refresh" ? (
                <Button type="button" variant="outline" onClick={refresh}>
                  <RefreshCw className="size-3.5" aria-hidden />
                  {nextAction.ctaLabel || "Refresh"}
                </Button>
              ) : null}
              {nextAction.ctaKind === "profile" && nextAction.ctaHref ? (
                <Button type="button" variant="outline" asChild>
                  <Link href={nextAction.ctaHref}>{nextAction.ctaLabel}</Link>
                </Button>
              ) : null}
              {nextAction.ctaKind === "current" && nextAction.ctaHref ? (
                <Button type="button" variant="outline" asChild>
                  <Link href={nextAction.ctaHref}>
                    {nextAction.ctaLabel || "View current"}
                  </Link>
                </Button>
              ) : null}
            </div>
          </SurfaceCardContent>
        </SurfaceCard>
      )}

      {empty || !contract ? (
        <SurfaceCard>
          <EmptyState
            icon={FileText}
            title={empty?.title ?? "No contract on file"}
            description={
              empty?.description ?? "Your brokerage has not issued an agreement yet."
            }
            actions={
              <Button asChild variant="outline">
                <Link href={routes.profile()}>Open profile</Link>
              </Button>
            }
          />
        </SurfaceCard>
      ) : (
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="grid gap-6">
            {/*
              Four facts and a four-step progression. They were eight equal
              label/value pairs, three of which — Sent, Viewed, Signed — are one
              sequence read as a set of unrelated dates, with a 36-character id
              in the middle of them.
            */}
            <SurfaceCard>
              <PanelHeader
                title="Agreement details"
                description={`Version ${contract.versionNumber} · ${contract.officeName}`}
                divided
              />
              <SurfaceCardContent className="grid gap-6">
                <dl className="grid gap-4 sm:grid-cols-3">
                  <ReadOnlyValue label="Effective">
                    {formatDate(contract.effectiveOn)}
                  </ReadOnlyValue>
                  <ReadOnlyValue label="Expires">
                    {contract.expiresOn ? (
                      formatDate(contract.expiresOn)
                    ) : (
                      <span className="text-muted-foreground">No end date</span>
                    )}
                  </ReadOnlyValue>
                  <ReadOnlyValue label="Party">
                    {contract.partyDisplayName}
                  </ReadOnlyValue>
                </dl>

                <div className="border-border/60 grid gap-3 border-t pt-5">
                  <h3 className="text-muted-foreground text-xs font-semibold tracking-[0.06em] uppercase">
                    Progress
                  </h3>
                  <Timeline
                    aria-label="Agreement progress"
                    items={progressItems(contract)}
                  />
                </div>

                <div className="border-border/60 flex flex-wrap items-baseline gap-x-2 gap-y-1 border-t pt-5">
                  <span className="text-muted-foreground text-xs font-semibold">
                    Contract id
                  </span>
                  {/*
                    Kept, because it is what support asks for, and demoted,
                    because nobody reads a UUID as part of understanding their
                    own agreement.
                  */}
                  <code className="text-muted-foreground font-mono text-xs break-all">
                    {contract.publicId}
                  </code>
                </div>
              </SurfaceCardContent>
            </SurfaceCard>

            {capabilities.canViewCommission ? (
              <SurfaceCard>
                <PanelHeader
                  title="Commission summary"
                  description="Plain-language overview. Mentor and referral are listed separately."
                />
                <SurfaceCardContent>
                  <CommissionSummary contract={contract} />
                </SurfaceCardContent>
              </SurfaceCard>
            ) : null}

            <SurfaceCard>
              <PanelHeader
                title="Legal document"
                description="Download if embedded preview is unavailable on your device."
              />
              <SurfaceCardContent>
                {state === "generating" ? (
                  <Callout tone="info" title="Preparing your PDF">
                    This usually takes a few seconds. Refresh above once it is ready.
                  </Callout>
                ) : state === "generation_failed" ? (
                  <Callout tone="destructive" title="The PDF could not be generated">
                    Ask your branch manager or the operations team to retry it. Your
                    agreement and its terms are unaffected.
                  </Callout>
                ) : (
                  <PdfPreview
                    key={contract.previewUrl ?? contract.publicId}
                    contract={contract}
                  />
                )}
              </SurfaceCardContent>
            </SurfaceCard>

            {/*
              A standing note about the whole page, so it gets the note's own
              shape instead of being the smallest type on the screen, unlabelled
              and floating under the last panel.
            */}
            <Callout tone="neutral">{disclaimer}</Callout>
          </div>

          <aside className="grid gap-6 self-start">
            <SurfaceCard>
              <PanelHeader
                title="Version history"
                description="Agreements and amendments you may view."
                headingLevel="h2"
              />
              <SurfaceCardContent>
                <HistoryList rows={history} />
              </SurfaceCardContent>
            </SurfaceCard>
          </aside>
        </div>
      )}
    </div>
  );
}

MyContract.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "My contract",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "My contract" },
        ],
      },
    },
  ] as const;
