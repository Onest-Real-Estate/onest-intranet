/** Client-side validators mirroring ``apps/user/us.py`` messages. */

const US_PHONE_RE = /^\(?(\d{3})\)?[-.\s]?(\d{3})[-.\s]?(\d{4})$/;
const US_ZIP_RE = /^\d{5}(?:-\d{4})?$/;

export const US_PHONE_ERROR = "Enter a valid US phone number, e.g. (202) 555-0100.";
export const US_ZIP_ERROR = "Enter a 5-digit ZIP code, or ZIP+4 (12345-6789).";

export function validateUsPhone(value: string): string | undefined {
  const raw = value.trim();
  if (!raw) {
    return "Enter a US phone number.";
  }
  if (!US_PHONE_RE.test(raw)) {
    return US_PHONE_ERROR;
  }
  return undefined;
}

export function validateUsZip(value: string): string | undefined {
  const raw = value.trim();
  if (!raw) {
    return "Enter a ZIP code.";
  }
  if (!US_ZIP_RE.test(raw)) {
    return US_ZIP_ERROR;
  }
  return undefined;
}
