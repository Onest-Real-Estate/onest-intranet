import { Head, Link, usePage } from "@inertiajs/react";
import {
  Building2,
  ImageOff,
  LayoutGrid,
  List,
  Mail,
  Phone,
  SearchX,
  Users,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  EmptyState,
  FilterControls,
  FilterField,
  PageHeader,
  Pagination,
  SearchControl,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { buildListUrl, visitListUrl } from "@/lib/list-query";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type {
  AgentDirectoryFilters,
  AgentDirectoryPageProps,
  AgentDirectoryPerson,
  FilterOption,
} from "@/types";

const ALL = "__all__";
const SEARCH_DEBOUNCE_MS = 300;

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: FilterOption[];
  onChange: (next: string) => void;
}) {
  return (
    <FilterField label={label} hideLabel>
      <Select
        value={value || ALL}
        onValueChange={(next) => onChange(next === ALL ? "" : next)}
      >
        <SelectTrigger size="sm" aria-label={label}>
          <SelectValue placeholder={`Any ${label.toLowerCase()}`} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>Any {label.toLowerCase()}</SelectItem>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </FilterField>
  );
}

function PersonHeadshot({ person }: { person: AgentDirectoryPerson }) {
  const [failed, setFailed] = useState(false);

  if (!person.headshotPath || failed) {
    return (
      <div
        className="bg-muted text-muted-foreground flex size-full items-center justify-center"
        aria-hidden
      >
        <ImageOff className="size-6" />
      </div>
    );
  }

  return (
    <img
      src={person.headshotPath}
      alt=""
      className="bg-muted size-full object-cover"
      onError={() => setFailed(true)}
    />
  );
}

function ContactActions({ person }: { person: AgentDirectoryPerson }) {
  return (
    <div className="flex flex-wrap gap-2">
      {person.workPhone ? (
        <Button type="button" variant="outline" size="sm" asChild>
          <a
            href={`tel:${person.workPhone}`}
            aria-label={`Call work phone for ${person.preferredName}`}
          >
            <Phone className="size-3.5" aria-hidden />
            Call work phone
          </a>
        </Button>
      ) : null}
      {person.workEmail ? (
        <Button type="button" variant="outline" size="sm" asChild>
          <a
            href={`mailto:${person.workEmail}`}
            aria-label={`Email ${person.preferredName} at work`}
          >
            <Mail className="size-3.5" aria-hidden />
            Email
          </a>
        </Button>
      ) : null}
    </div>
  );
}

function PersonCard({ person, view }: { person: AgentDirectoryPerson; view: string }) {
  const isList = view === "list";
  const detailHref = routes.agent_directory_detail(person.id);
  const roleLabel = person.roles.join(", ") || "Team member";
  const specialtyLabel = person.specialties.map((item) => item.name).join(", ");
  const languageLabel = person.languages.map((item) => item.name).join(", ");

  return (
    <li
      className={cn(
        "border-border overflow-hidden rounded-lg border",
        isList
          ? "grid gap-3 p-3 sm:grid-cols-[5rem_minmax(0,1fr)_auto] sm:items-center"
          : "grid grid-rows-[9rem_minmax(0,1fr)]",
      )}
    >
      <div
        className={cn(
          "bg-muted overflow-hidden",
          isList ? "size-20 shrink-0 rounded-md" : "size-full",
        )}
      >
        <PersonHeadshot person={person} />
      </div>
      <div className={cn("grid min-w-0 gap-1", !isList && "p-3 pt-2")}>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <Link
            href={detailHref}
            className="text-foreground text-sm font-medium hover:underline"
          >
            {person.preferredName}
          </Link>
          <span className="text-muted-foreground text-xs">{roleLabel}</span>
        </div>
        {person.office ? (
          <p className="text-muted-foreground text-sm">
            {person.office.pathLabel || person.office.name}
          </p>
        ) : (
          <p className="text-muted-foreground text-sm">No office assigned</p>
        )}
        {person.licenseStateName ? (
          <p className="text-muted-foreground text-xs">
            Licensed in {person.licenseStateName}
          </p>
        ) : null}
        {specialtyLabel ? (
          <p className="text-muted-foreground text-xs">{specialtyLabel}</p>
        ) : null}
        {languageLabel ? (
          <p className="text-muted-foreground text-xs">{languageLabel}</p>
        ) : null}
      </div>
      <div
        className={cn(
          "flex flex-col gap-2",
          isList ? "sm:items-end" : "border-border border-t px-3 py-2",
        )}
      >
        <ContactActions person={person} />
        <Button type="button" variant="outline" size="sm" asChild>
          <Link href={detailHref}>View profile</Link>
        </Button>
      </div>
    </li>
  );
}

/**
 * Privacy-aware peer Agent Directory — company-wide active/on-leave people
 * with URL-backed search and filters.
 */
export default function AgentDirectory() {
  const { people, filterOptions, empty } = usePage<AgentDirectoryPageProps>().props;
  const filters = people.filters as AgentDirectoryFilters;
  const [query, setQuery] = useState(filters.q ?? "");
  const view = filters.view === "list" ? "list" : "grid";
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  useEffect(() => {
    setQuery(filters.q ?? "");
  }, [filters.q]);

  useEffect(() => {
    const serverQuery = filtersRef.current.q ?? "";
    if (query === serverQuery) {
      return;
    }
    const handle = window.setTimeout(() => {
      const current = filtersRef.current;
      visitListUrl(
        buildListUrl(routes.agent_directory(), window.location.search, {
          q: query,
          page: 1,
          filters: { ...current, q: query },
        }),
      );
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [query]);

  function visit(next: Partial<AgentDirectoryFilters>, page?: number) {
    const merged = { ...filters, ...next };
    visitListUrl(
      buildListUrl(routes.agent_directory(), window.location.search, {
        q: next.q !== undefined ? next.q : query,
        page,
        filters: merged,
      }),
    );
  }

  const activeCount = (
    ["office", "region", "role", "licenseState", "specialty", "language"] as const
  ).filter((key) => Boolean(filters[key])).length;

  return (
    <div className="grid gap-8">
      <Head title="Agent directory" />
      <PageHeader
        title="Agent directory"
        description="Find colleagues by name, office, role, license, specialty, or language."
      />

      <SurfaceCard>
        <SurfaceCardContent className="grid gap-4">
          <FilterControls
            activeCount={activeCount + Number(Boolean(filters.q))}
            onReset={() => {
              setQuery("");
              visit({
                q: "",
                office: "",
                region: "",
                role: "",
                licenseState: "",
                specialty: "",
                language: "",
              });
            }}
          >
            <SearchControl
              value={query}
              onValueChange={setQuery}
              onSearch={(next) => visit({ q: next }, 1)}
              onClear={() => {
                setQuery("");
                visit({ q: "" }, 1);
              }}
              label="Search the directory"
              placeholder="Search by name or office"
              className="min-w-56"
            />
            <FilterSelect
              label="Office"
              value={filters.office}
              options={filterOptions.offices}
              onChange={(office) => visit({ office })}
            />
            <FilterSelect
              label="Region"
              value={filters.region}
              options={filterOptions.regions}
              onChange={(region) => visit({ region })}
            />
            <FilterSelect
              label="Role"
              value={filters.role}
              options={filterOptions.roles}
              onChange={(role) => visit({ role })}
            />
            <FilterSelect
              label="License state"
              value={filters.licenseState}
              options={filterOptions.licenseStates}
              onChange={(licenseState) => visit({ licenseState })}
            />
            <FilterSelect
              label="Specialty"
              value={filters.specialty}
              options={filterOptions.specialties}
              onChange={(specialty) => visit({ specialty })}
            />
            <FilterSelect
              label="Language"
              value={filters.language}
              options={filterOptions.languages}
              onChange={(language) => visit({ language })}
            />
            <div className="flex items-end gap-1">
              <Button
                type="button"
                size="sm"
                variant={view === "grid" ? "default" : "outline"}
                aria-pressed={view === "grid"}
                aria-label="Grid view"
                onClick={() => visit({ view: "grid" })}
              >
                <LayoutGrid className="size-4" />
              </Button>
              <Button
                type="button"
                size="sm"
                variant={view === "list" ? "default" : "outline"}
                aria-pressed={view === "list"}
                aria-label="List view"
                onClick={() => visit({ view: "list" })}
              >
                <List className="size-4" />
              </Button>
            </div>
          </FilterControls>
        </SurfaceCardContent>
      </SurfaceCard>

      {empty ? (
        <SurfaceCard>
          <EmptyState
            icon={empty.kind === "no-people" ? Users : SearchX}
            title={empty.title}
            description={empty.description}
            actions={
              empty.kind === "no-results" ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setQuery("");
                    visit({
                      q: "",
                      office: "",
                      region: "",
                      role: "",
                      licenseState: "",
                      specialty: "",
                      language: "",
                    });
                  }}
                >
                  Clear filters
                </Button>
              ) : undefined
            }
          />
        </SurfaceCard>
      ) : (
        <>
          <ul
            className={cn(
              "grid gap-4",
              view === "grid" ? "sm:grid-cols-2 xl:grid-cols-3" : "grid-cols-1",
            )}
          >
            {people.items.map((person) => (
              <PersonCard key={person.id} person={person} view={view} />
            ))}
          </ul>
          <Pagination
            pagination={people.pagination}
            onPageChange={(page) => visit({}, page)}
          />
        </>
      )}

      {!empty && people.items.some((person) => !person.office) ? (
        <SurfaceCard>
          <SurfaceCardContent className="text-muted-foreground flex items-start gap-2 text-sm">
            <Building2 className="mt-0.5 size-4 shrink-0" aria-hidden />
            Some people have no office assigned yet; their cards still show contact
            details when available.
          </SurfaceCardContent>
        </SurfaceCard>
      ) : null}
    </div>
  );
}

AgentDirectory.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Agent directory",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Agent directory" },
        ],
      },
    },
  ] as const;
