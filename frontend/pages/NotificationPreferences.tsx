import { Head, Link, router, usePage } from "@inertiajs/react";
import { ArrowLeft, Lock } from "lucide-react";
import { useMemo, useState } from "react";

import {
  FormActionBar,
  FormErrorSummary,
  PageHeader,
  SurfaceCard,
  SurfaceCardContent,
  SurfaceCardDescription,
  SurfaceCardHeader,
  SurfaceCardTitle,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { routes } from "@/lib/routes";
import type {
  NotificationCategoryPreference,
  NotificationPreferencesPageProps,
} from "@/types";

/** Editable cells, keyed by the field name the server expects. */
type Draft = Record<string, boolean>;

function initialDraft(categories: NotificationCategoryPreference[]): Draft {
  const draft: Draft = {};
  for (const category of categories) {
    for (const cell of category.channels) {
      if (!cell.locked) {
        draft[cell.field] = cell.enabled;
      }
    }
  }
  return draft;
}

function formatSaved(value: string | null): string {
  if (!value) {
    return "Not changed yet — you are on the defaults.";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "Saved."
    : `Last saved ${parsed.toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })}.`;
}

/**
 * One category's row: what arrives in it, and one control per channel.
 *
 * A locked cell is rendered, not hidden. Hiding it would read as "this
 * category does not use email", when what is true is "you are always told".
 * The checkbox is present, checked, disabled, and followed by the sentence
 * explaining why — and it posts nothing, because the server has no field for
 * it either.
 */
function CategoryRow({
  category,
  draft,
  disabled,
  onChange,
}: {
  category: NotificationCategoryPreference;
  draft: Draft;
  disabled: boolean;
  onChange: (field: string, value: boolean) => void;
}) {
  const channelLabels =
    usePage<NotificationPreferencesPageProps>().props.preferences.channels;

  return (
    <fieldset className="border-border/60 grid gap-3 border-t py-5 first:border-t-0 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start sm:gap-6">
      {/* The legend names the group for assistive technology and has to be the
          fieldset's first child to do so, so the visible heading below is a
          plain paragraph rather than the legend itself. */}
      <legend className="sr-only">{category.label}</legend>
      <div className="grid min-w-0 gap-1">
        <p className="text-foreground text-sm font-semibold">{category.label}</p>
        <p className="text-muted-foreground text-sm leading-5">
          {category.description}
        </p>
        {category.mandatory ? (
          <p className="text-muted-foreground flex items-start gap-1.5 text-sm leading-5">
            <Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            <span>{category.mandatoryReason}</span>
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-3 sm:justify-end">
        {category.channels.map((cell) => {
          const channel = channelLabels.find((item) => item.key === cell.key);
          const id = `pref-${cell.field}`;
          const noteId = cell.locked ? `${id}-note` : undefined;
          const checked = cell.locked ? cell.enabled : (draft[cell.field] ?? false);
          return (
            <div key={cell.field} className="flex min-w-32 items-start gap-2">
              <Checkbox
                id={id}
                name={cell.field}
                checked={checked}
                disabled={cell.locked || disabled}
                aria-describedby={noteId}
                onCheckedChange={(next) => onChange(cell.field, next === true)}
              />
              <div className="grid gap-1">
                <Label htmlFor={id} className="text-sm font-normal">
                  {channel?.label ?? cell.key}
                </Label>
                {cell.locked ? (
                  <p id={noteId} className="text-muted-foreground text-xs leading-4">
                    {cell.lockedReason}
                  </p>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}

/**
 * The reader's own notification settings.
 *
 * Two things this page is careful about. It never pretends a locked control is
 * a choice — mandatory notices and the in-app record show as switched on and
 * disabled, with the reason next to them. And it never presents a cell as
 * "off by default" without saying so: every value here is the server's
 * resolved answer, so a category added after somebody last saved arrives at
 * its documented default rather than silently off.
 */
export default function NotificationPreferences() {
  const { preferences, notificationsHref, errors } =
    usePage<NotificationPreferencesPageProps>().props;
  const [draft, setDraft] = useState<Draft>(() => initialDraft(preferences.categories));
  const [saving, setSaving] = useState(false);

  const saved = useMemo(
    () => initialDraft(preferences.categories),
    [preferences.categories],
  );
  const dirty = useMemo(
    () => Object.keys(saved).some((field) => saved[field] !== draft[field]),
    [saved, draft],
  );

  function change(field: string, value: boolean) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  function submit() {
    setSaving(true);
    router.post(
      routes.notification_preferences_submit(),
      { ...draft },
      {
        preserveScroll: true,
        onFinish: () => setSaving(false),
      },
    );
  }

  return (
    <div className="grid gap-6">
      <Head title="Notification settings" />
      <PageHeader
        title="Notification settings"
        description="Choose which notifications also reach your inbox. Everything is always recorded in the hub, and required legal, compliance, and security notices are always sent."
        meta={<span>{formatSaved(preferences.policy.updatedAt)}</span>}
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href={notificationsHref}>
              <ArrowLeft className="size-4" aria-hidden />
              Notification centre
            </Link>
          </Button>
        }
      />

      <FormErrorSummary errors={errors} title="These settings were not saved" />

      {preferences.policy.outdated ? (
        <SurfaceCard>
          <SurfaceCardContent>
            <p className="text-muted-foreground text-sm leading-5">
              New notification categories have been added since you last saved. Your
              existing choices are unchanged; anything new is set to its default until
              you decide otherwise.
            </p>
          </SurfaceCardContent>
        </SurfaceCard>
      ) : null}

      <SurfaceCard>
        <SurfaceCardHeader>
          <SurfaceCardTitle>What you are told about</SurfaceCardTitle>
          <SurfaceCardDescription>
            {preferences.channels
              .map((channel) => `${channel.label}: ${channel.description}`)
              .join(" ")}
          </SurfaceCardDescription>
        </SurfaceCardHeader>
        <SurfaceCardContent>
          <div className="grid">
            {preferences.categories.map((category) => (
              <CategoryRow
                key={category.key}
                category={category}
                draft={draft}
                disabled={saving}
                onChange={change}
              />
            ))}
          </div>
        </SurfaceCardContent>
      </SurfaceCard>

      <FormActionBar
        status={
          saving
            ? "Saving your settings…"
            : dirty
              ? "You have unsaved changes."
              : "Your settings are up to date."
        }
      >
        <Button type="button" onClick={submit} disabled={saving || !dirty}>
          Save settings
        </Button>
      </FormActionBar>
    </div>
  );
}

NotificationPreferences.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Notification settings",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Notifications", href: routes.notifications() },
          {
            label: "Settings",
            href: routes.notification_preferences(),
          },
        ],
        back: { label: "Back to notifications", href: routes.notifications() },
      },
      variant: "standard",
    },
  ] as const;
