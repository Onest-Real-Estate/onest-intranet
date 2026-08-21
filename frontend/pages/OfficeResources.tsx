import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  Building2,
  Download,
  ExternalLink,
  FileText,
  FolderOpen,
  Link2,
  ScrollText,
  SearchX,
} from "lucide-react";
import { useState } from "react";

import {
  EmptyState,
  PageHeader,
  PanelHeader,
  SearchControl,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { routes } from "@/lib/routes";
import type {
  OfficeResourceGroup,
  OfficeResourceItem,
  OfficeResourcesPageProps,
} from "@/types";

const TYPE_ICONS = {
  content: ScrollText,
  link: Link2,
  file: FileText,
} as const;

function ResourceRow({ item }: { item: OfficeResourceItem }) {
  const Icon = TYPE_ICONS[item.resourceType] ?? ScrollText;
  return (
    <li className="border-border grid min-w-0 gap-2 rounded-lg border p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start sm:gap-4">
      <div className="grid min-w-0 gap-0.5">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <Icon className="text-muted-foreground size-4 shrink-0" aria-hidden />
          <span className="text-foreground text-sm font-medium">{item.title}</span>
          <Badge variant="secondary" className="rounded-full">
            {item.sourceLabel}
          </Badge>
        </div>
        {item.summary ? (
          <p className="text-muted-foreground text-sm">{item.summary}</p>
        ) : null}
        {item.body ? (
          <p className="text-muted-foreground mt-1 text-sm whitespace-pre-line">
            {item.body}
          </p>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-2 sm:justify-end">
        {item.resourceType === "link" && item.url ? (
          <Button type="button" variant="outline" size="sm" asChild>
            <a href={item.url} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="size-3.5" aria-hidden />
              Open link
            </a>
          </Button>
        ) : null}
        {item.resourceType === "file" && item.downloadUrl ? (
          <Button type="button" variant="outline" size="sm" asChild>
            {/* Plain anchor: an Inertia visit would XHR the bytes instead of
                triggering the browser's download flow. */}
            <a href={item.downloadUrl} download>
              <Download className="size-3.5 shrink-0" aria-hidden />
              <span className="max-w-48 truncate">
                {item.fileName ? `Download (${item.fileName})` : "Download"}
              </span>
            </a>
          </Button>
        ) : null}
      </div>
    </li>
  );
}

function ResourceGroupCard({ group }: { group: OfficeResourceGroup }) {
  return (
    <SurfaceCard>
      <PanelHeader title={group.label} headingLevel="h2" divided />
      <SurfaceCardContent className="grid gap-3">
        <ul className="grid gap-3">
          {group.items.map((item) => (
            <ResourceRow key={`${item.sourceLevel}-${item.slug}`} item={item} />
          ))}
        </ul>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

/**
 * Location-specific instructions, procedures, contacts, links, and files for
 * the signed-in user's effective office scope (office > region > company).
 */
export default function OfficeResources() {
  const { groups, filters, categories, empty } =
    usePage<OfficeResourcesPageProps>().props;
  const [q, setQ] = useState(filters.q);
  const [category, setCategory] = useState(filters.category);

  function visit(next: { q?: string; category?: string }) {
    const mergedQ = next.q ?? q;
    const mergedCategory = next.category ?? category;
    router.get(
      routes.office_resources(),
      {
        ...(mergedQ ? { q: mergedQ } : {}),
        ...(mergedCategory ? { category: mergedCategory } : {}),
      },
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  const filtered = Boolean(filters.q || filters.category);

  return (
    <div className="grid gap-10">
      <Head title="Office resources" />
      <PageHeader
        title="Office resources"
        description="Instructions, procedures, contacts, links, and files for your branch."
      />

      {empty ? (
        <SurfaceCard>
          <EmptyState
            icon={empty.kind === "no-office" ? Building2 : SearchX}
            title={empty.title}
            description={empty.description}
            actions={
              empty.kind === "no-office" ? (
                <Button asChild variant="outline">
                  <Link href={routes.profile()}>Open profile</Link>
                </Button>
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setQ("");
                    setCategory("");
                    router.get(
                      routes.office_resources(),
                      {},
                      {
                        preserveState: true,
                        preserveScroll: true,
                        replace: true,
                      },
                    );
                  }}
                >
                  Clear search
                </Button>
              )
            }
          />
        </SurfaceCard>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_13rem]">
            <SearchControl
              label="Search resources"
              value={q}
              onValueChange={setQ}
              onSearch={(next) => visit({ q: next })}
              onClear={() => visit({ q: "" })}
              placeholder="Search instructions and procedures"
            />
            <Select
              value={category || "all"}
              onValueChange={(value) => {
                const next = value === "all" ? "" : value;
                setCategory(next);
                visit({ category: next });
              }}
            >
              <SelectTrigger aria-label="Filter by category">
                <SelectValue placeholder="All categories" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {categories.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {groups.length ? (
            <div className="grid gap-6">
              {groups.map((group) => (
                <ResourceGroupCard key={group.key} group={group} />
              ))}
            </div>
          ) : (
            <SurfaceCard>
              <EmptyState
                icon={filtered ? SearchX : FolderOpen}
                title={filtered ? "No matching resources" : "No resources yet"}
                description={
                  filtered
                    ? "Nothing matches your search. Try a different term or category."
                    : "Your office has no published resources yet. Ask your branch administrator."
                }
              />
            </SurfaceCard>
          )}
        </>
      )}
    </div>
  );
}

OfficeResources.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Office resources",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Office resources" },
        ],
      },
    },
  ] as const;
