import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  AlertTriangle,
  Download,
  ExternalLink,
  FileText,
  FileWarning,
  Loader2,
  PenLine,
  RefreshCw,
} from "lucide-react";
import { useId, useState } from "react";

import {
  EmptyState,
  MetricCard,
  MetricStrip,
  PageHeader,
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { routes } from "@/lib/routes";
import type {
  MyContractDetail,
  MyContractHistoryRow,
  MyContractPageProps,
  MyContractState,
} from "@/types";
import type { StatusTone } from "@/types/design-system";

function toTone(raw: string): StatusTone {
  if (raw === "danger") return "destructive";
  if (
    raw === "neutral" ||
    raw === "info" ||
    raw === "success" ||
    raw === "warning" ||
    raw === "destructive"
  ) {
    return raw;
  }
  return "neutral";
}

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

      <div className="grid gap-4 md:grid-cols-2">
        <section
          aria-labelledby="mentor-terms"
          className="border-border grid gap-2 rounded-lg border p-4"
        >
          <h3 id="mentor-terms" className="text-sm font-semibold">
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

        <section
          aria-labelledby="referral-terms"
          className="border-border grid gap-2 rounded-lg border p-4"
        >
          <h3 id="referral-terms" className="text-sm font-semibold">
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
      {rows.map((row) => (
        <li key={row.publicId}>
          {row.isFocus ? (
            <div className="border-border bg-muted/40 flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3">
              <div className="grid min-w-0 gap-0.5">
                <span className="text-sm font-medium">Version {row.versionNumber}</span>
                <span className="text-muted-foreground text-xs">
                  Effective {formatDate(row.effectiveOn)}
                  {row.expiresOn ? ` · Expires ${formatDate(row.expiresOn)}` : ""}
                </span>
              </div>
              <Badge variant="secondary">Current view</Badge>
            </div>
          ) : (
            <Link
              href={row.href}
              className="border-border hover:bg-muted/30 focus-visible:ring-ring flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 transition-colors focus-visible:ring-2 focus-visible:outline-none"
              preserveScroll
            >
              <div className="grid min-w-0 gap-0.5">
                <span className="text-sm font-medium">Version {row.versionNumber}</span>
                <span className="text-muted-foreground text-xs">
                  Effective {formatDate(row.effectiveOn)} · {row.statusLabel}
                </span>
              </div>
              <StatusBadge
                status={{
                  label: row.statusLabel,
                  tone: toTone(row.statusTone),
                }}
              />
            </Link>
          )}
        </li>
      ))}
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
      <Button type="button">
        <PenLine className="size-3.5" aria-hidden />
        Sign contract
      </Button>
    );
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          aria-label="Sign contract — one-click signing is not available yet"
          aria-disabled
          onClick={(event) => event.preventDefault()}
        >
          <PenLine className="size-3.5" aria-hidden />
          Sign contract
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        One-click signing is not wired up yet. You can still review and download the
        PDF.
      </TooltipContent>
    </Tooltip>
  );
}

function stateIcon(state: MyContractState) {
  switch (state) {
    case "generating":
      return Loader2;
    case "generation_failed":
      return FileWarning;
    case "awaiting_signature":
      return PenLine;
    case "no_contract":
      return FileText;
    default:
      return AlertTriangle;
  }
}

/**
 * Self-service My Contract: status, plain-language terms, secure PDF, history.
 */
export default function MyContract() {
  const { state, nextAction, contract, history, capabilities, disclaimer, empty } =
    usePage<MyContractPageProps>().props;

  const Icon = stateIcon(state);

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
                tone: toTone(contract.statusTone),
              }}
            />
          ) : null
        }
      />

      {empty || !contract ? null : (
        <SurfaceCard>
          <SurfaceCardContent className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="grid min-w-0 gap-2">
              <div className="flex items-start gap-3">
                <Icon
                  className={`text-muted-foreground mt-0.5 size-5 shrink-0 ${
                    state === "generating" ? "animate-spin" : ""
                  }`}
                  aria-hidden
                />
                <div className="grid gap-1">
                  <h2 className="text-base font-semibold">{nextAction.title}</h2>
                  <p className="text-muted-foreground text-sm">
                    {nextAction.description}
                  </p>
                </div>
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
            <SurfaceCard>
              <PanelHeader
                title="Agreement details"
                description={`Version ${contract.versionNumber} · ${contract.officeName}`}
              />
              <SurfaceCardContent>
                <dl className="grid gap-4 sm:grid-cols-2">
                  <div className="grid gap-1">
                    <dt className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                      Effective
                    </dt>
                    <dd className="text-sm">{formatDate(contract.effectiveOn)}</dd>
                  </div>
                  <div className="grid gap-1">
                    <dt className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                      Expires
                    </dt>
                    <dd className="text-sm">{formatDate(contract.expiresOn)}</dd>
                  </div>
                  <div className="grid gap-1 sm:col-span-2">
                    <dt className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                      Contract id
                    </dt>
                    <dd className="font-mono text-xs break-all">{contract.publicId}</dd>
                  </div>
                  <div className="grid gap-1">
                    <dt className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                      Sent
                    </dt>
                    <dd className="text-sm">{formatStamp(contract.sentAt)}</dd>
                  </div>
                  <div className="grid gap-1">
                    <dt className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                      Viewed
                    </dt>
                    <dd className="text-sm">{formatStamp(contract.viewedAt)}</dd>
                  </div>
                  <div className="grid gap-1">
                    <dt className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                      Signed
                    </dt>
                    <dd className="text-sm">{formatStamp(contract.signedAt)}</dd>
                  </div>
                  <div className="grid gap-1">
                    <dt className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                      Party
                    </dt>
                    <dd className="text-sm">{contract.partyDisplayName}</dd>
                  </div>
                </dl>
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
                  <p className="text-muted-foreground flex items-center gap-2 text-sm">
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                    Generating your PDF…
                  </p>
                ) : state === "generation_failed" ? (
                  <p className="text-muted-foreground text-sm">
                    The PDF could not be generated. Ask your branch manager or
                    operations team to retry.
                  </p>
                ) : (
                  <PdfPreview
                    key={contract.previewUrl ?? contract.publicId}
                    contract={contract}
                  />
                )}
              </SurfaceCardContent>
            </SurfaceCard>

            <p className="text-muted-foreground text-xs">{disclaimer}</p>
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
