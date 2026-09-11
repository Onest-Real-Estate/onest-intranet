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
export interface MarketingDraftDefaults {
  owner_office?: string;
  title?: string;
  description?: string;
  usage_instructions?: string;
  category?: string;
  asset_type?: string;
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
 * Shorter than the workspace: enough for a draft to exist and be aimed. Files,
 * jurisdiction, brands, and lifecycle belong in the workspace after save.
 */
export function MarketingCreateFields({
  defaults,
  offices,
  categories,
  assetTypes,
  audience,
}: {
  defaults: MarketingDraftDefaults;
  offices: AnnouncementOfficeOption[];
  categories: FilterOption[];
  assetTypes: FilterOption[];
  audience: AnnouncementAudienceOptions;
}) {
  return (
    <>
      <FormField>
        <FormLabel htmlFor="mc-title" required>
          Title
        </FormLabel>
        <Input
          id="mc-title"
          name="title"
          defaultValue={defaults.title ?? ""}
          required
          maxLength={180}
        />
      </FormField>

      <FormField>
        <FormLabel htmlFor="mc-description" optional>
          Description
        </FormLabel>
        <Textarea
          id="mc-description"
          name="description"
          rows={3}
          defaultValue={defaults.description ?? ""}
        />
        <FormDescription>
          Short summary shown in the library and on the detail page.
        </FormDescription>
      </FormField>

      <FormField>
        <FormLabel htmlFor="mc-owner" required>
          Owning office
        </FormLabel>
        <NativeSelect
          id="mc-owner"
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
          <FormLabel htmlFor="mc-category">Category</FormLabel>
          <NativeSelect
            id="mc-category"
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
          <FormLabel htmlFor="mc-asset-type" required>
            Asset type
          </FormLabel>
          <NativeSelect
            id="mc-asset-type"
            name="asset_type"
            defaultValue={defaults.asset_type ?? ""}
            required
          >
            <option value="">Choose a type</option>
            {assetTypes.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </NativeSelect>
        </FormField>
      </div>
      <FormDescription>
        Category is required to publish, not to save. You can set it later in the
        workspace.
      </FormDescription>

      <fieldset className="grid gap-3">
        <legend className="text-sm font-semibold">Audience</legend>
        <FormDescription>
          Choices combine as a union — anyone matching any one of them can see it. Only
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
