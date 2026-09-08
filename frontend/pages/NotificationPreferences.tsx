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
import { toFormData } from "@/lib/form-data";
import { routes } from "@/lib/routes";
import type {
  NotificationCategoryPreference,
  NotificationChannelDefinition,
  NotificationPreferencesPageProps,
} from "@/types";

/** Editable cells, keyed by the field name the server expects. */
type Draft = Record<string, boolean>;

/**
 * One grid template for the header row and every category row.
 *
 * The channel columns are fixed and the category column takes the rest. An
 * `auto` channel column sizes to its widest content, which on this page is a
 * sentence — it would squeeze the category text into a one-word ribbon.
 */
const ROW_GRID =
  "grid gap-x-4 gap-y-3 sm:grid-cols-[minmax(0,1fr)_6rem_6rem] sm:items-start";

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
 * One category: what arrives in it on the left, one control per channel on the
 * right, aligned to the column headers above.
 *
 * A locked cell is rendered, not hidden. Hiding it would read as "this category
 * does not use email", when what is true is "you are always told". It shows
 * checked and disabled, and points at the sentence that says why — which lives
 * once per reason rather than beside every checkbox, so the row stays a row.
 */
function CategoryRow({
  category,
  channels,
  draft,
  disabled,
  onChange,
}: {
  category: NotificationCategoryPreference;
  channels: NotificationChannelDefinition[];
  draft: Draft;
  disabled: boolean;
  onChange: (field: string, value: boolean) => void;
}) {
  const mandatoryNoteId = `mandatory-${category.key}`;

  return (
    <fieldset className="border-border/60 min-w-0 border-t py-5 first:border-t-0">
      {/* Names the group for assistive technology. It has to be the fieldset's
          first child to do that, so the visible heading below is a paragraph. */}
      <legend className="sr-only">{category.label}</legend>
      <div className={ROW_GRID}>
        <div className="grid min-w-0 gap-1">
          <p className="text-foreground text-sm font-semibold">{category.label}</p>
          <p className="text-muted-foreground text-sm leading-5">
            {category.description}
          </p>
          {category.mandatory ? (
            <p
              id={mandatoryNoteId}
              className="text-muted-foreground flex items-start gap-1.5 text-sm leading-5"
            >
              <Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              <span>{category.mandatoryReason}</span>
            </p>
          ) : null}
        </div>

        {category.channels.map((cell) => {
          const channel = channels.find((item) => item.key === cell.key);
          const id = `pref-${cell.field}`;
          const describedBy = !cell.locked
            ? undefined
            : category.mandatory && channel?.configurable !== false
              ? mandatoryNoteId
              : `channel-note-${cell.key}`;
          const checked = cell.locked ? cell.enabled : (draft[cell.field] ?? false);
          return (
            <div
              key={cell.field}
              className="flex items-center gap-2 sm:justify-center sm:pt-0.5"
            >
              <Checkbox
                id={id}
                name={cell.field}
                checked={checked}
                disabled={cell.locked || disabled}
                aria-describedby={describedBy}
                onCheckedChange={(next) => onChange(cell.field, next === true)}
              />
              {/* Visible on narrow screens, where there is no column header to
                  read the checkbox against. */}
              <Label htmlFor={id} className="text-sm font-normal sm:sr-only">
                {channel?.label ?? cell.key}
              </Label>
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
 * disabled, with the reason nearby. And it never presents a cell as "off by
 * default" without saying so: every value here is the server's resolved
 * answer, so a category added after somebody last saved arrives at its
 * documented default rather than silently off.
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
    router.post(routes.notification_preferences_submit(), toFormData({ ...draft }), {
      preserveScroll: true,
      onFinish: () => setSaving(false),
    });
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
          <SurfaceCardTitle>How you are told</SurfaceCardTitle>
          <SurfaceCardDescription>
            Two ways one notification can reach you. One of them is the record and stays
            on.
          </SurfaceCardDescription>
        </SurfaceCardHeader>
        <SurfaceCardContent>
          <dl className="grid gap-4 sm:grid-cols-2">
            {preferences.channels.map((channel) => (
              <div key={channel.key} className="grid min-w-0 gap-1">
                <dt className="text-foreground text-sm font-semibold">
                  {channel.label}
                </dt>
                <dd className="text-muted-foreground text-sm leading-5">
                  {channel.description}
                </dd>
                {channel.configurable ? null : (
                  <dd
                    id={`channel-note-${channel.key}`}
                    className="text-muted-foreground flex items-start gap-1.5 text-sm leading-5"
                  >
                    <Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                    <span>{channel.lockedReason}</span>
                  </dd>
                )}
              </div>
            ))}
          </dl>
        </SurfaceCardContent>
      </SurfaceCard>

      <SurfaceCard>
        <SurfaceCardHeader>
          <SurfaceCardTitle>What you are told about</SurfaceCardTitle>
          <SurfaceCardDescription>
            Turn off anything you would rather pick up in the hub. Required notices have
            no switch.
          </SurfaceCardDescription>
        </SurfaceCardHeader>
        <SurfaceCardContent>
          {/* Column headers, wide screens only. Each checkbox carries its own
              label for assistive technology, so this is decoration. */}
          <div
            className={`${ROW_GRID} border-border/60 hidden border-b pb-3 sm:grid`}
            aria-hidden
          >
            <span />
            {preferences.channels.map((channel) => (
              <span
                key={channel.key}
                className="text-muted-foreground text-center text-xs font-semibold tracking-[0.06em] uppercase"
              >
                {channel.label}
              </span>
            ))}
          </div>

          <div className="grid">
            {preferences.categories.map((category) => (
              <CategoryRow
                key={category.key}
                category={category}
                channels={preferences.channels}
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
          { label: "Settings", href: routes.notification_preferences() },
        ],
        back: { label: "Back to notifications", href: routes.notifications() },
      },
      variant: "standard",
    },
  ] as const;
