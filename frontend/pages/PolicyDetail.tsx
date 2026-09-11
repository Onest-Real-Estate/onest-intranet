import { Head, Link, router, usePage } from "@inertiajs/react";
import { ArrowLeft, Download, FileText, ShieldCheck } from "lucide-react";
import { useState } from "react";

import {
  EmptyState,
  FormErrorSummary,
  PageHeader,
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
  toStatusTone,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/announcements";
import { toFormData } from "@/lib/form-data";
import { routes } from "@/lib/routes";
import type { ComplianceFileItem, PolicyDetailPageProps } from "@/types";

function DocumentRow({ file }: { file: ComplianceFileItem }) {
  const href = file.url || routes.policy_document_file(file.id);
  return (
    <li className="border-border grid gap-2 rounded-lg border p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:gap-4">
      <div className="flex min-w-0 items-start gap-3">
        <div className="bg-muted text-muted-foreground flex size-14 shrink-0 items-center justify-center rounded-md">
          <FileText className="size-5" aria-hidden />
        </div>
        <div className="grid min-w-0 gap-0.5">
          <span className="text-foreground truncate text-sm font-medium">
            {file.displayName}
          </span>
          <span className="text-muted-foreground text-xs">
            {formatBytes(file.byteSize)} · {file.mediaType}
          </span>
        </div>
      </div>
      <Button type="button" variant="outline" size="sm" asChild>
        {/* Plain anchor: an Inertia visit would XHR the bytes instead of
            triggering the browser's download flow. */}
        <a href={href} download>
          <Download className="size-3.5 shrink-0" aria-hidden />
          Download
        </a>
      </Button>
    </li>
  );
}

export default function PolicyDetail() {
  const { policy, errors } = usePage<PolicyDetailPageProps>().props;
  const [submitting, setSubmitting] = useState(false);

  function acknowledge() {
    setSubmitting(true);
    router.post(
      routes.policy_acknowledge(policy.id),
      toFormData({
        expectedChecksum: policy.contentChecksum,
        disclosureVersion: policy.disclosureVersion,
      }),
      { onFinish: () => setSubmitting(false) },
    );
  }

  return (
    <>
      <Head title={policy.title} />
      <div className="grid gap-8">
        <PageHeader
          title={policy.title}
          description={policy.summary || undefined}
          meta={
            <span className="flex flex-wrap items-center gap-2">
              <StatusBadge
                status={{
                  label: policy.status.label,
                  tone: toStatusTone(policy.status.tone),
                }}
              />
              {policy.category ? (
                <StatusBadge
                  status={{
                    label: policy.category.label,
                    tone: toStatusTone(policy.category.tone),
                  }}
                />
              ) : null}
              {policy.isMandatory ? (
                <StatusBadge status={{ label: "Mandatory", tone: "warning" }} />
              ) : null}
              {policy.acknowledged ? (
                <StatusBadge status={{ label: "Acknowledged", tone: "success" }} />
              ) : policy.waived ? (
                <StatusBadge status={{ label: "Waived", tone: "neutral" }} />
              ) : policy.required ? (
                <StatusBadge status={{ label: "Ack required", tone: "destructive" }} />
              ) : null}
              <span className="text-muted-foreground text-sm">
                {policy.versionLabel}
                {policy.publishedAt
                  ? ` · Published ${new Date(policy.publishedAt).toLocaleDateString()}`
                  : ""}
              </span>
            </span>
          }
          actions={
            <Button variant="outline" size="sm" asChild>
              <Link href={routes.policies_compliance()}>
                <ArrowLeft className="size-4" aria-hidden />
                All policies
              </Link>
            </Button>
          }
        />

        <FormErrorSummary errors={errors} />

        {policy.body ? (
          <SurfaceCard>
            <PanelHeader divided title="Policy" />
            <SurfaceCardContent>
              <div className="text-muted-foreground text-sm leading-6 whitespace-pre-line">
                {policy.body}
              </div>
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}

        {(policy.jurisdictionStateCodes.length > 0 ||
          policy.effectiveAt ||
          policy.expiresAt) && (
          <SurfaceCard>
            <PanelHeader divided title="Scope & dates" />
            <SurfaceCardContent className="grid gap-2 text-sm">
              {policy.jurisdictionStateCodes.length > 0 ? (
                <p>
                  <span className="text-foreground font-medium">Jurisdictions: </span>
                  <span className="text-muted-foreground">
                    {policy.jurisdictionStateCodes.join(", ")}
                  </span>
                </p>
              ) : null}
              {policy.effectiveAt ? (
                <p>
                  <span className="text-foreground font-medium">Effective: </span>
                  <span className="text-muted-foreground">
                    {new Date(policy.effectiveAt).toLocaleString()}
                  </span>
                </p>
              ) : null}
              {policy.expiresAt ? (
                <p>
                  <span className="text-foreground font-medium">Expires: </span>
                  <span className="text-muted-foreground">
                    {new Date(policy.expiresAt).toLocaleString()}
                  </span>
                </p>
              ) : null}
            </SurfaceCardContent>
          </SurfaceCard>
        )}

        <SurfaceCard>
          <PanelHeader
            divided
            title="Documents"
            description="Supporting files for this policy version."
            meta={
              <span className="text-muted-foreground text-xs font-medium tabular-nums">
                {policy.documents.length}{" "}
                {policy.documents.length === 1 ? "file" : "files"}
              </span>
            }
          />
          <SurfaceCardContent>
            {policy.documents.length === 0 ? (
              <EmptyState
                icon={FileText}
                compact
                title="No documents yet"
                description="Files for this policy will appear here when they are ready."
              />
            ) : (
              <ul className="grid gap-3" aria-label="Policy documents">
                {policy.documents.map((file) => (
                  <DocumentRow key={file.id} file={file} />
                ))}
              </ul>
            )}
          </SurfaceCardContent>
        </SurfaceCard>

        {policy.canAcknowledge ||
        policy.acknowledged ||
        policy.waived ||
        policy.acknowledgementDisclosure ? (
          <SurfaceCard>
            <PanelHeader
              divided
              title="Acknowledgement"
              description={
                policy.dueAt && policy.required
                  ? `Due ${new Date(policy.dueAt).toLocaleDateString()}.`
                  : undefined
              }
            />
            <SurfaceCardContent className="grid gap-4">
              {policy.acknowledgementDisclosure ? (
                <p className="text-muted-foreground text-sm leading-6 whitespace-pre-line">
                  {policy.acknowledgementDisclosure}
                </p>
              ) : null}
              {policy.acknowledged ? (
                <p className="text-sm">
                  You acknowledged this policy
                  {policy.acknowledgedAt
                    ? ` on ${new Date(policy.acknowledgedAt).toLocaleString()}`
                    : ""}
                  .
                </p>
              ) : null}
              {policy.waived ? (
                <p className="text-muted-foreground text-sm">
                  Acknowledgement was waived for your account.
                </p>
              ) : null}
              {policy.canAcknowledge ? (
                <Button
                  type="button"
                  disabled={submitting}
                  aria-busy={submitting || undefined}
                  onClick={acknowledge}
                >
                  <ShieldCheck className="size-4" aria-hidden />I acknowledge this
                  policy
                </Button>
              ) : null}
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}
      </div>
    </>
  );
}

PolicyDetail.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Policies & compliance",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          {
            label: "Policies & compliance",
            href: routes.policies_compliance(),
          },
        ],
      },
    },
  ] as const;
