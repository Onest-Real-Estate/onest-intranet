import { FormField, FormLabel, NativeSelect } from "@/components/design-system";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { FilterOption } from "@/types";

export interface InventoryFormDefaults {
  name?: string;
  ownerId?: number | string;
  category?: string;
  trackingMode?: string;
  condition?: string;
  assetId?: string;
  serialNumber?: string;
  totalQuantity?: number | string;
  storageLocation?: string;
  notes?: string;
  internalNotes?: string;
  replacementValue?: string;
  replacementCurrency?: string;
  photoIsPublic?: boolean;
}

export function InventoryFormFields({
  defaults,
  categories,
  trackingModes,
  conditions,
  writableOffices,
  canViewSensitive = false,
  includeTrackingFields = true,
}: {
  defaults: InventoryFormDefaults;
  categories: FilterOption[];
  trackingModes: FilterOption[];
  conditions: FilterOption[];
  writableOffices: { id: number; label: string; kind: string }[];
  canViewSensitive?: boolean;
  includeTrackingFields?: boolean;
}) {
  return (
    <>
      <FormField>
        <FormLabel htmlFor="inv-name" required>
          Name
        </FormLabel>
        <Input
          id="inv-name"
          name="name"
          defaultValue={defaults.name ?? ""}
          required
          maxLength={200}
        />
      </FormField>

      <FormField>
        <FormLabel htmlFor="inv-owner_office" required>
          Owning office
        </FormLabel>
        <NativeSelect
          id="inv-owner_office"
          name="owner_office"
          defaultValue={String(defaults.ownerId ?? writableOffices[0]?.id ?? "")}
          required
          disabled={writableOffices.length === 0}
        >
          {writableOffices.length === 0 ? (
            <option value="">No offices in your administrative scope</option>
          ) : (
            writableOffices.map((office) => (
              <option key={office.id} value={office.id}>
                {office.label}
              </option>
            ))
          )}
        </NativeSelect>
        {writableOffices.length === 0 ? (
          <p className="text-muted-foreground text-xs">
            You can manage inventory, but no assignable office is in your effective
            scope. Ask an administrator to confirm your role assignment.
          </p>
        ) : null}
      </FormField>

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField>
          <FormLabel htmlFor="inv-category" required>
            Category
          </FormLabel>
          <NativeSelect
            id="inv-category"
            name="category"
            defaultValue={defaults.category ?? categories[0]?.value ?? ""}
          >
            {categories.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </NativeSelect>
        </FormField>
        <FormField>
          <FormLabel htmlFor="inv-condition" required>
            Condition
          </FormLabel>
          <NativeSelect
            id="inv-condition"
            name="condition"
            defaultValue={defaults.condition ?? conditions[0]?.value ?? ""}
          >
            {conditions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </NativeSelect>
        </FormField>
      </div>

      {includeTrackingFields ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField>
            <FormLabel htmlFor="inv-tracking_mode" required>
              Tracking
            </FormLabel>
            <NativeSelect
              id="inv-tracking_mode"
              name="tracking_mode"
              defaultValue={defaults.trackingMode ?? "serialized"}
            >
              {trackingModes.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </NativeSelect>
          </FormField>
          <FormField>
            <FormLabel htmlFor="inv-total_quantity">Total quantity</FormLabel>
            <Input
              id="inv-total_quantity"
              name="total_quantity"
              type="number"
              min={1}
              defaultValue={String(defaults.totalQuantity ?? 1)}
            />
          </FormField>
        </div>
      ) : null}

      {canViewSensitive && includeTrackingFields ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField>
            <FormLabel htmlFor="inv-asset_id">Asset ID</FormLabel>
            <Input
              id="inv-asset_id"
              name="asset_id"
              defaultValue={defaults.assetId ?? ""}
              maxLength={64}
            />
          </FormField>
          <FormField>
            <FormLabel htmlFor="inv-serial_number">Serial number</FormLabel>
            <Input
              id="inv-serial_number"
              name="serial_number"
              defaultValue={defaults.serialNumber ?? ""}
              maxLength={128}
            />
          </FormField>
        </div>
      ) : null}

      <FormField>
        <FormLabel htmlFor="inv-storage_location">Storage location</FormLabel>
        <Input
          id="inv-storage_location"
          name="storage_location"
          defaultValue={defaults.storageLocation ?? ""}
          maxLength={200}
        />
      </FormField>

      <FormField>
        <FormLabel htmlFor="inv-notes">Notes</FormLabel>
        <Textarea
          id="inv-notes"
          name="notes"
          defaultValue={defaults.notes ?? ""}
          rows={3}
        />
      </FormField>

      {canViewSensitive ? (
        <>
          <FormField>
            <FormLabel htmlFor="inv-internal_notes">Internal notes</FormLabel>
            <Textarea
              id="inv-internal_notes"
              name="internal_notes"
              defaultValue={defaults.internalNotes ?? ""}
              rows={3}
            />
          </FormField>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField>
              <FormLabel htmlFor="inv-replacement_value">Replacement value</FormLabel>
              <Input
                id="inv-replacement_value"
                name="replacement_value"
                defaultValue={defaults.replacementValue ?? ""}
              />
            </FormField>
            <FormField>
              <FormLabel htmlFor="inv-replacement_currency">Currency</FormLabel>
              <Input
                id="inv-replacement_currency"
                name="replacement_currency"
                defaultValue={defaults.replacementCurrency ?? "USD"}
                maxLength={3}
              />
            </FormField>
          </div>
        </>
      ) : null}
    </>
  );
}
