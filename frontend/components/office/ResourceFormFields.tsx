import { FormField, FormLabel } from "@/components/design-system";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { FilterOption } from "@/types";

const SELECT_CLASS =
  "bg-background border-border text-foreground h-9 w-full rounded-md border px-3 text-sm";

function HelpText({ children }: { children: string }) {
  return <p className="text-muted-foreground text-xs">{children}</p>;
}

/** Default values for one resource form render (resource, error draft, or blank). */
export interface ResourceFormDefaults {
  slug?: string;
  title?: string;
  summary?: string;
  category?: string;
  resourceType?: string;
  body?: string;
  url?: string;
  ownerId?: number | null;
  sortOrder?: number;
  isActive?: boolean;
  startsAt?: string;
  endsAt?: string;
}

/**
 * The shared OfficeResource field set, used by both the full-page editor and
 * the create slide-over so the two never drift.
 */
export function ResourceFormFields({
  defaults,
  categories,
  types,
  writableOffices,
  includeFile = false,
}: {
  defaults: ResourceFormDefaults;
  categories: FilterOption[];
  types: FilterOption[];
  writableOffices: { id: number; label: string; kind: string }[];
  /** Show the file picker (create-sheet mode only). */
  includeFile?: boolean;
}) {
  return (
    <>
      <FormField>
        <FormLabel htmlFor="rf-title" required>
          Title
        </FormLabel>
        <Input
          id="rf-title"
          name="title"
          defaultValue={defaults.title ?? ""}
          required
          maxLength={150}
        />
      </FormField>

      <FormField>
        <FormLabel htmlFor="rf-slug">Slug</FormLabel>
        <Input
          id="rf-slug"
          name="slug"
          defaultValue={defaults.slug ?? ""}
          maxLength={80}
          pattern="[a-z0-9\-]*"
        />
        <HelpText>
          Identity across scopes — a closer-scope slug overrides a wider one. Blank
          derives from the title.
        </HelpText>
      </FormField>

      <FormField>
        <FormLabel htmlFor="rf-summary">Summary</FormLabel>
        <Input
          id="rf-summary"
          name="summary"
          defaultValue={defaults.summary ?? ""}
          maxLength={255}
        />
      </FormField>

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField>
          <FormLabel htmlFor="rf-category" required>
            Category
          </FormLabel>
          <select
            id="rf-category"
            name="category"
            defaultValue={defaults.category ?? "general"}
            className={SELECT_CLASS}
          >
            {categories.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </FormField>
        <FormField>
          <FormLabel htmlFor="rf-resource_type" required>
            Type
          </FormLabel>
          <select
            id="rf-resource_type"
            name="resource_type"
            defaultValue={defaults.resourceType ?? "content"}
            className={SELECT_CLASS}
          >
            {types.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </FormField>
      </div>

      <FormField>
        <FormLabel htmlFor="rf-body">Content</FormLabel>
        <Textarea
          id="rf-body"
          name="body"
          rows={5}
          defaultValue={defaults.body ?? ""}
        />
        <HelpText>Required for content resources.</HelpText>
      </FormField>

      <FormField>
        <FormLabel htmlFor="rf-url">Destination URL</FormLabel>
        <Input
          id="rf-url"
          name="url"
          type="url"
          defaultValue={defaults.url ?? ""}
          placeholder="https://"
        />
        <HelpText>Link resources only. Must start with https://</HelpText>
      </FormField>

      {includeFile ? (
        <FormField>
          <FormLabel htmlFor="rf-file">File</FormLabel>
          <Input
            id="rf-file"
            name="file"
            type="file"
            accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.txt,.csv"
          />
          <HelpText>File resources only. Protected storage; up to 10 MB.</HelpText>
        </FormField>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3">
        <FormField>
          <FormLabel htmlFor="rf-owner_office" required>
            Owning office
          </FormLabel>
          {/* Native select so the value posts with the form; the server
              re-validates the boundary either way. */}
          <select
            id="rf-owner_office"
            name="owner_office"
            defaultValue={String(defaults.ownerId ?? writableOffices[0]?.id ?? "")}
            className={SELECT_CLASS}
          >
            {writableOffices.map((option) => (
              <option key={option.id} value={String(option.id)}>
                {option.label}
              </option>
            ))}
          </select>
        </FormField>
        <FormField>
          <FormLabel htmlFor="rf-sort_order">Sort order</FormLabel>
          <Input
            id="rf-sort_order"
            name="sort_order"
            type="number"
            min={0}
            defaultValue={defaults.sortOrder ?? 0}
          />
        </FormField>
        <FormField>
          <FormLabel htmlFor="rf-is_active">State</FormLabel>
          <label className="border-border flex h-9 items-center gap-2 rounded-md border px-3 text-sm">
            <input
              type="checkbox"
              name="is_active"
              defaultChecked={defaults.isActive ?? false}
              className="accent-primary size-4"
            />
            Active
          </label>
        </FormField>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField>
          <FormLabel htmlFor="rf-starts_at">Publishes on</FormLabel>
          <Input
            id="rf-starts_at"
            name="starts_at"
            type="date"
            defaultValue={defaults.startsAt ?? ""}
          />
        </FormField>
        <FormField>
          <FormLabel htmlFor="rf-ends_at">Expires after</FormLabel>
          <Input
            id="rf-ends_at"
            name="ends_at"
            type="date"
            defaultValue={defaults.endsAt ?? ""}
          />
        </FormField>
      </div>
    </>
  );
}
