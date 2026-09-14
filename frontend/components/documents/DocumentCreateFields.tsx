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

export interface DocumentDraftDefaults {
  owner_office?: string;
  family_key?: string;
  name?: string;
  description?: string;
  category?: string;
  audience_company?: string;
  audience_roles?: string[];
  audience_regions?: string[];
  audience_offices?: string[];
}

function checked(values: string[] | undefined, value: string | number): boolean {
  return (values ?? []).includes(String(value));
}

export function DocumentCreateFields({
  defaults,
  offices,
  categories,
  audience,
}: {
  defaults: DocumentDraftDefaults;
  offices: AnnouncementOfficeOption[];
  categories: FilterOption[];
  audience: AnnouncementAudienceOptions;
}) {
  return (
    <>
      <FormField>
        <FormLabel htmlFor="dc-name" required>
          Name
        </FormLabel>
        <Input
          id="dc-name"
          name="name"
          defaultValue={defaults.name ?? ""}
          required
          maxLength={180}
        />
      </FormField>

      <FormField>
        <FormLabel htmlFor="dc-description" optional>
          Description
        </FormLabel>
        <Textarea
          id="dc-description"
          name="description"
          rows={3}
          defaultValue={defaults.description ?? ""}
        />
        <FormDescription>
          Short summary shown in the library and on the detail page.
        </FormDescription>
      </FormField>

      <FormField>
        <FormLabel htmlFor="dc-owner" required>
          Owning office
        </FormLabel>
        <NativeSelect
          id="dc-owner"
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

      <FormField>
        <FormLabel htmlFor="dc-key" optional>
          Family key
        </FormLabel>
        <Input
          id="dc-key"
          name="family_key"
          defaultValue={defaults.family_key ?? ""}
          maxLength={80}
        />
        <FormDescription>
          Stable identity across versions. Generated from the name when left empty.
        </FormDescription>
      </FormField>

      <FormField>
        <FormLabel htmlFor="dc-category">Category</FormLabel>
        <NativeSelect
          id="dc-category"
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
        <FormDescription>
          Category is required to publish, not to save. You can set it later in the
          workspace.
        </FormDescription>
      </FormField>

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
