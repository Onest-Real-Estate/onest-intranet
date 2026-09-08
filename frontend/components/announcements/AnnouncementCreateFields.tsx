import {
  FormDescription,
  FormField,
  FormLabel,
  NativeSelect,
} from "@/components/design-system";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type {
  AnnouncementAudienceOptions,
  AnnouncementOfficeOption,
  FilterOption,
} from "@/types";

/** What the server echoed back after a rejected create, or nothing on a fresh open. */
export interface AnnouncementDraftDefaults {
  owner_office?: string;
  title?: string;
  summary?: string;
  body?: string;
  category?: string;
  priority?: string;
  audience_company?: string;
  audience_roles?: string[];
  audience_regions?: string[];
  audience_offices?: string[];
}

function checked(values: string[] | undefined, value: string | number): boolean {
  return (values ?? []).includes(String(value));
}

/**
 * The create-drawer field set.
 *
 * Deliberately shorter than the workspace form: it asks for what a draft needs
 * to exist and be aimed at somebody, and nothing else. The window, the call to
 * action, hero images, and every lifecycle decision belong to the workspace the
 * author lands on after saving — a drawer that tried to carry them would be a
 * page with a narrower column.
 *
 * Native inputs throughout, because the drawer posts as a real form. Every
 * option here comes from the server's grant-bounded querysets, and the save
 * re-checks the same boundary regardless of what is submitted.
 */
export function AnnouncementCreateFields({
  defaults,
  offices,
  categories,
  priorities,
  audience,
}: {
  defaults: AnnouncementDraftDefaults;
  offices: AnnouncementOfficeOption[];
  categories: FilterOption[];
  priorities: FilterOption[];
  audience: AnnouncementAudienceOptions;
}) {
  return (
    <>
      <FormField>
        <FormLabel htmlFor="ac-title" required>
          Title
        </FormLabel>
        <Input
          id="ac-title"
          name="title"
          defaultValue={defaults.title ?? ""}
          required
          maxLength={180}
        />
      </FormField>

      <FormField>
        <FormLabel htmlFor="ac-summary" optional>
          Summary
        </FormLabel>
        <Input
          id="ac-summary"
          name="summary"
          defaultValue={defaults.summary ?? ""}
          maxLength={280}
        />
        <FormDescription>
          One line, shown under the headline in the feed.
        </FormDescription>
      </FormField>

      <FormField>
        <FormLabel htmlFor="ac-body" required>
          Body
        </FormLabel>
        <Textarea
          id="ac-body"
          name="body"
          rows={6}
          defaultValue={defaults.body ?? ""}
        />
      </FormField>

      <FormField>
        <FormLabel htmlFor="ac-owner" required>
          Owning office
        </FormLabel>
        <NativeSelect
          id="ac-owner"
          name="owner_office"
          defaultValue={defaults.owner_office ?? ""}
          required
        >
          <option value="">Choose an office</option>
          {offices.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </NativeSelect>
        <FormDescription>
          Who is publishing. Permanent once saved, and never widens the audience on its
          own.
        </FormDescription>
      </FormField>

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField>
          <FormLabel htmlFor="ac-category">Category</FormLabel>
          <NativeSelect
            id="ac-category"
            name="category"
            defaultValue={defaults.category ?? ""}
          >
            <option value="">Not chosen yet</option>
            {categories.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </NativeSelect>
        </FormField>

        <FormField>
          <FormLabel htmlFor="ac-priority">Priority</FormLabel>
          <NativeSelect
            id="ac-priority"
            name="priority"
            defaultValue={defaults.priority ?? ""}
          >
            <option value="">Not chosen yet</option>
            {priorities.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </NativeSelect>
        </FormField>
      </div>
      <FormDescription>
        Both are required to publish, not to save. You can choose them later in the
        workspace.
      </FormDescription>

      <fieldset className="grid gap-3">
        <legend className="text-sm font-semibold">Audience</legend>
        <FormDescription>
          Choices combine as a union — anyone matching any one of them receives it. Only
          what you may address is listed.
        </FormDescription>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            name="audience_company"
            value="on"
            defaultChecked={defaults.audience_company === "on"}
            className="accent-primary size-4"
          />
          Everyone at the brokerage
        </label>
        {!audience.canTargetCompany ? (
          <FormDescription>
            Only a brokerage-wide administrator can address everyone, so this will be
            refused for your grant.
          </FormDescription>
        ) : null}

        {audience.regions.length > 0 ? (
          <div className="grid gap-1.5">
            <p className="text-muted-foreground text-xs font-semibold">
              Regions and everything under them
            </p>
            {audience.regions.map((option) => (
              <label key={option.value} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  name="audience_regions"
                  value={option.value}
                  defaultChecked={checked(defaults.audience_regions, option.value)}
                  className="accent-primary size-4"
                />
                {option.label}
              </label>
            ))}
          </div>
        ) : null}

        {audience.offices.length > 0 ? (
          <div className="grid gap-1.5">
            <p className="text-muted-foreground text-xs font-semibold">
              Single offices
            </p>
            {audience.offices.map((option) => (
              <label key={option.value} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  name="audience_offices"
                  value={option.value}
                  defaultChecked={checked(defaults.audience_offices, option.value)}
                  className="accent-primary size-4"
                />
                {option.label}
              </label>
            ))}
          </div>
        ) : null}

        {audience.roles.length > 0 ? (
          <div className="grid gap-1.5">
            <p className="text-muted-foreground text-xs font-semibold">Roles</p>
            {audience.roles.map((option) => (
              <label key={option.value} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  name="audience_roles"
                  value={option.value}
                  defaultChecked={checked(defaults.audience_roles, option.value)}
                  className="accent-primary size-4"
                />
                {option.label}
              </label>
            ))}
          </div>
        ) : null}

        <FormDescription>
          Naming individual people needs the workspace, where the scoped typeahead
          lives.
        </FormDescription>
      </fieldset>
    </>
  );
}
