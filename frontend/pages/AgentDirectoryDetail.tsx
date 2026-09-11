import { Head, Link, usePage } from "@inertiajs/react";
import { ArrowLeft, Building2, ImageOff, Mail, Phone } from "lucide-react";
import { useState } from "react";

import {
  PageHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import type { AgentDirectoryDetailPageProps, AgentDirectoryPerson } from "@/types";

function PersonHeadshot({ person }: { person: AgentDirectoryPerson }) {
  const [failed, setFailed] = useState(false);

  if (!person.headshotPath || failed) {
    return (
      <div
        className="bg-muted text-muted-foreground flex aspect-square size-full max-w-xs items-center justify-center rounded-lg"
        role="img"
        aria-label="No headshot available"
      >
        <ImageOff className="size-10" aria-hidden />
      </div>
    );
  }

  return (
    <img
      src={person.headshotPath}
      alt={`Headshot of ${person.preferredName}`}
      className="bg-muted aspect-square size-full max-w-xs rounded-lg object-cover"
      onError={() => setFailed(true)}
    />
  );
}

export default function AgentDirectoryDetail() {
  const { person } = usePage<AgentDirectoryDetailPageProps>().props;
  const roleLabel = person.roles.join(", ") || "Team member";

  return (
    <div className="grid gap-8">
      <Head title={person.preferredName} />
      <PageHeader
        title={person.preferredName}
        description={roleLabel}
        meta={
          <Button type="button" variant="ghost" size="sm" asChild>
            <Link href={routes.agent_directory()}>
              <ArrowLeft className="size-4" aria-hidden />
              Back to directory
            </Link>
          </Button>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <PersonHeadshot person={person} />

        <SurfaceCard>
          <SurfaceCardContent className="grid gap-6">
            <section className="grid gap-2">
              <h2 className="text-foreground text-sm font-medium">Office</h2>
              {person.office ? (
                <p className="text-muted-foreground text-sm">
                  {person.office.pathLabel || person.office.name}
                  {person.office.regionName ? ` · ${person.office.regionName}` : ""}
                </p>
              ) : (
                <p className="text-muted-foreground flex items-center gap-2 text-sm">
                  <Building2 className="size-4 shrink-0" aria-hidden />
                  No office assigned
                </p>
              )}
            </section>

            <section className="grid gap-2">
              <h2 className="text-foreground text-sm font-medium">Work contact</h2>
              <p className="text-muted-foreground text-sm">
                External contact methods for this colleague. These open your phone or
                mail app — they are not internal Hub messages.
              </p>
              <div className="flex flex-wrap gap-2">
                {person.workPhone ? (
                  <Button type="button" variant="outline" size="sm" asChild>
                    <a
                      href={`tel:${person.workPhone}`}
                      aria-label={`Call work phone for ${person.preferredName}`}
                    >
                      <Phone className="size-3.5" aria-hidden />
                      {person.workPhone}
                    </a>
                  </Button>
                ) : (
                  <p className="text-muted-foreground text-sm">No work phone on file</p>
                )}
                {person.workEmail ? (
                  <Button type="button" variant="outline" size="sm" asChild>
                    <a
                      href={`mailto:${person.workEmail}`}
                      aria-label={`Email ${person.preferredName} at work`}
                    >
                      <Mail className="size-3.5" aria-hidden />
                      {person.workEmail}
                    </a>
                  </Button>
                ) : null}
              </div>
            </section>

            {person.licenseStateName ? (
              <section className="grid gap-1">
                <h2 className="text-foreground text-sm font-medium">License state</h2>
                <p className="text-muted-foreground text-sm">
                  {person.licenseStateName}
                </p>
              </section>
            ) : null}

            {person.specialties.length > 0 ? (
              <section className="grid gap-1">
                <h2 className="text-foreground text-sm font-medium">Specialties</h2>
                <ul className="text-muted-foreground list-inside list-disc text-sm">
                  {person.specialties.map((item) => (
                    <li key={item.code}>{item.name}</li>
                  ))}
                </ul>
              </section>
            ) : null}

            {person.languages.length > 0 ? (
              <section className="grid gap-1">
                <h2 className="text-foreground text-sm font-medium">Languages</h2>
                <ul className="text-muted-foreground list-inside list-disc text-sm">
                  {person.languages.map((item) => (
                    <li key={item.code}>{item.name}</li>
                  ))}
                </ul>
              </section>
            ) : null}
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </div>
  );
}

AgentDirectoryDetail.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Agent directory",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Agent directory", href: routes.agent_directory() },
          { label: "Profile" },
        ],
      },
    },
  ] as const;
