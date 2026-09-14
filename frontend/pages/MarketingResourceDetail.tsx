import { Head, Link, usePage } from "@inertiajs/react";
import { ArrowLeft, Download, FileText } from "lucide-react";

import {
  EmptyState,
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
import { routes } from "@/lib/routes";
import type { MarketingFileItem, MarketingResourceDetailPageProps } from "@/types";

function ExportRow({ file }: { file: MarketingFileItem }) {
  const href = file.url || routes.marketing_resource_export(file.id);
  return (
    <li className="border-border grid gap-2 rounded-lg border p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:gap-4">
      <div className="flex min-w-0 items-start gap-3">
        {file.isImage && (file.variants.thumb || file.previewUrl) ? (
          <img
            src={file.variants.thumb || file.previewUrl}
            alt=""
            className="border-border size-14 shrink-0 rounded-md border object-cover"
          />
        ) : (
          <div className="bg-muted text-muted-foreground flex size-14 shrink-0 items-center justify-center rounded-md">
            <FileText className="size-5" aria-hidden />
          </div>
        )}
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

export default function MarketingResourceDetail() {
  const { asset } = usePage<MarketingResourceDetailPageProps>().props;

  return (
    <>
      <Head title={asset.title} />
      <div className="grid gap-8">
        <PageHeader
          title={asset.title}
          description={asset.description || undefined}
          meta={
            <span className="flex flex-wrap items-center gap-2">
              <StatusBadge
                status={{
                  label: asset.assetType.label,
                  tone: toStatusTone(asset.assetType.tone),
                }}
              />
              {asset.category ? (
                <StatusBadge
                  status={{
                    label: asset.category.label,
                    tone: toStatusTone(asset.category.tone),
                  }}
                />
              ) : null}
              <span className="text-muted-foreground text-sm">
                {asset.versionLabel}
                {asset.publishedAt
                  ? ` · Published ${new Date(asset.publishedAt).toLocaleDateString()}`
                  : ""}
              </span>
            </span>
          }
          actions={
            <Button variant="outline" size="sm" asChild>
              <Link href={routes.marketing_resources()}>
                <ArrowLeft className="size-4" aria-hidden />
                Back to marketing
              </Link>
            </Button>
          }
        />

        {asset.usageInstructions ? (
          <SurfaceCard>
            <PanelHeader divided title="How to use this asset" />
            <SurfaceCardContent>
              <p className="text-muted-foreground text-sm leading-6 whitespace-pre-line">
                {asset.usageInstructions}
              </p>
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}

        {(asset.jurisdictionStateCodes.length > 0 || asset.brandCodes.length > 0) && (
          <SurfaceCard>
            <PanelHeader divided title="Scope notes" />
            <SurfaceCardContent className="grid gap-2 text-sm">
              {asset.jurisdictionStateCodes.length > 0 ? (
                <p>
                  <span className="text-foreground font-medium">Jurisdictions: </span>
                  <span className="text-muted-foreground">
                    {asset.jurisdictionStateCodes.join(", ")}
                  </span>
                </p>
              ) : null}
              {asset.brandCodes.length > 0 ? (
                <p>
                  <span className="text-foreground font-medium">Brands: </span>
                  <span className="text-muted-foreground">
                    {asset.brandCodes.join(", ")}
                  </span>
                </p>
              ) : null}
            </SurfaceCardContent>
          </SurfaceCard>
        )}

        <SurfaceCard>
          <PanelHeader
            divided
            title="Downloads"
            description="Export files approved for use. Source working files are not available here."
            meta={
              <span className="text-muted-foreground text-xs font-medium tabular-nums">
                {asset.exports.length} {asset.exports.length === 1 ? "file" : "files"}
              </span>
            }
          />
          <SurfaceCardContent>
            {asset.exports.length === 0 ? (
              <EmptyState
                icon={FileText}
                compact
                title="No export files yet"
                description="Files for this asset will appear here when they are ready."
              />
            ) : (
              <ul className="grid gap-3" aria-label="Export downloads">
                {asset.exports.map((file) => (
                  <ExportRow key={file.id} file={file} />
                ))}
              </ul>
            )}
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </>
  );
}

MarketingResourceDetail.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Marketing",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Marketing", href: routes.marketing_resources() },
        ],
      },
      variant: "standard",
    },
  ] as const;
