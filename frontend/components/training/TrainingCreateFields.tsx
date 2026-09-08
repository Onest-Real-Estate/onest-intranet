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
export interface TrainingDraftDefaults {
  owner_office?: string;
  title?: string;
  summary?: string;
  body?: string;
  category?: string;
  content_type?: string;
  is_required?: string;
  audience_company?: string;
  audience_roles?: string[];
  audience_regions?: string[];
  audience_offices?: string[];
}

function checked(values: string[] | undefined, value: string | number): boolean {
  return (values ?? []).includes(String(value));
}

/**
 * The create-drawer field set for training content.
 *
 * Deliberately shorter than the workspace form: enough to save a draft and land
 * in the workspace for media, scheduling, and lifecycle decisions.
 */
export function TrainingCreateFields({
  defaults,
  offices,
  categories,
  contentTypes,
  audience,
}: {
  defaults: TrainingDraftDefaults;
  offices: AnnouncementOfficeOption[];
  categories: FilterOption[];
  contentTypes: FilterOption[];
  audience: AnnouncementAudienceOptions;
}) {
  return (
    <>
      <FormField>
        <FormLabel htmlFor="tc-title" required>
          Title
        </FormLabel>
        <Input
          id="tc-title"
          name="title"
          defaultValue={defaults.title ?? ""}
          required
          maxLength={180}
        />
      </FormField>

      <FormField>
        <FormLabel htmlFor="tc-summary" optional>
          Summary
        </FormLabel>
        <Input
          id="tc-summary"
          name="summary"
          defaultValue={defaults.summary ?? ""}
          maxLength={280}
        />
        <FormDescription>
          One line, shown under the headline in the library.
        </FormDescription>
      </FormField>

      <FormField>
        <FormLabel htmlFor="tc-body" optional>
          Body
        </FormLabel>
        <Textarea
          id="tc-body"
          name="body"
          rows={6}
          defaultValue={defaults.body ?? ""}
        />
        <FormDescription>
          You can refine the body in the workspace after saving.
        </FormDescription>
      </FormField>

      <FormField>
        <FormLabel htmlFor="tc-owner" required>
          Owning office
        </FormLabel>
        <NativeSelect
          id="tc-owner"
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
          <FormLabel htmlFor="tc-category">Category</FormLabel>
          <NativeSelect
            id="tc-category"
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
          <FormLabel htmlFor="tc-content-type">Content type</FormLabel>
          <NativeSelect
            id="tc-content-type"
            name="content_type"
            defaultValue={defaults.content_type ?? ""}
          >
            <option value="">Not chosen yet</option>
            {contentTypes.map((option) => (
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

      <FormField>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            name="is_required"
            value="on"
            defaultChecked={defaults.is_required === "on"}
            className="accent-primary size-4"
          />
          Required training for the matched audience
        </label>
      </FormField>

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
