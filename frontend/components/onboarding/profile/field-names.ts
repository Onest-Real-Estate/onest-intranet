import type { OnboardingProfileSectionCode, SelfProfileValues } from "@/types";

/**
 * Django field name → camelCase prop, mirroring `forms.SELF_PROFILE_FIELD_MAP`.
 * Section membership is not repeated here: it comes from the server's field
 * policy (`profileFlow.fields[name].section`).
 */
export const PROP_FOR_FIELD: Record<string, keyof SelfProfileValues> = {
  first_name: "firstName",
  last_name: "lastName",
  preferred_name: "preferredName",
  phone_number: "phoneNumber",
  preferred_contact_method: "preferredContactMethod",
  street_address: "streetAddress",
  city: "city",
  state: "state",
  zip_code: "zipCode",
  office: "officeId",
  license_number: "licenseNumber",
  license_state: "licenseState",
  license_expires_on: "licenseExpiresOn",
  mls_number: "mlsNumber",
  nrds_number: "nrdsNumber",
  bio: "bio",
  languages: "languages",
  website_url: "websiteUrl",
  linkedin_url: "linkedinUrl",
  facebook_url: "facebookUrl",
  instagram_url: "instagramUrl",
  x_url: "xUrl",
};

export const SECTION_ORDER: OnboardingProfileSectionCode[] = [
  "identity",
  "contact",
  "credentials",
  "review",
];

/** Whether the values the page opened with already differ from what is saved. */
export function valuesDiffer(
  fields: string[],
  initial: SelfProfileValues,
  saved: SelfProfileValues,
): boolean {
  return fields.some((field) => {
    const prop = PROP_FOR_FIELD[field];
    return prop ? JSON.stringify(initial[prop]) !== JSON.stringify(saved[prop]) : false;
  });
}
