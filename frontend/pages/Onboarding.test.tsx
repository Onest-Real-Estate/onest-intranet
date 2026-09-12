import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import Onboarding from "@/pages/Onboarding";
import type {
  OnboardingFieldPolicy,
  OnboardingPageProps,
  OnboardingProfileSectionCode,
  SelfProfileValues,
} from "@/types";

type BeforeHandler = (event: {
  detail: { visit: { method: string; only: string[]; url: URL } };
}) => boolean | undefined;

const inertia = vi.hoisted(() => ({
  props: {} as OnboardingPageProps,
  beforeHandlers: [] as BeforeHandler[],
  // What Inertia would restore from this history entry's remembered state.
  remembered: null as unknown,
  rememberSpy: vi.fn(),
}));

const router = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  reload: vi.fn(),
  visit: vi.fn(),
  on: vi.fn(),
}));

const transport = vi.hoisted(() => ({
  uploadHeadshot: vi.fn(),
  removeHeadshot: vi.fn(),
}));

vi.mock("@inertiajs/react", async () => {
  const { useState } = await import("react");
  return {
    usePage: () => ({ props: inertia.props, url: "/onboarding" }),
    Head: () => null,
    Link: ({ href, children }: { href: string; children: ReactNode }) => (
      <a href={href}>{children}</a>
    ),
    router,
    useRemember: <T,>(initialState: T) => {
      const [state, setState] = useState<T>(
        (inertia.remembered as T | null) ?? initialState,
      );
      const remember = (next: T) => {
        inertia.rememberSpy(next);
        setState(next);
      };
      return [state, remember] as const;
    },
  };
});

vi.mock(
  "@/components/onboarding/profile/headshot-transport",
  async (importOriginal) => {
    const actual =
      await importOriginal<
        typeof import("@/components/onboarding/profile/headshot-transport")
      >();
    return { ...actual, ...transport };
  },
);

const { HeadshotRequestError } = await import(
  "@/components/onboarding/profile/headshot-transport"
);

function policy(
  label: string,
  section: OnboardingFieldPolicy["section"],
  overrides: Partial<OnboardingFieldPolicy> = {},
): OnboardingFieldPolicy {
  return {
    label,
    section,
    required: false,
    owner: "agent",
    readOnly: false,
    guidance: "",
    ...overrides,
  };
}

const FIELDS: Record<string, OnboardingFieldPolicy> = {
  headshot: policy("Profile photo", "identity", {
    required: true,
    guidance: "A clear, recent photo of you on your own.",
  }),
  first_name: policy("First name", "identity", {
    required: true,
    owner: "microsoft",
    readOnly: true,
  }),
  last_name: policy("Last name", "identity", {
    required: true,
    owner: "microsoft",
    readOnly: true,
  }),
  preferred_name: policy("Preferred name", "identity", {
    guidance: "Only if colleagues call you something else.",
  }),
  phone_number: policy("Phone number", "contact", { required: true }),
  preferred_contact_method: policy("Preferred contact method", "contact"),
  street_address: policy("Street address", "contact", { required: true }),
  city: policy("City", "contact", { required: true }),
  state: policy("State", "contact", { required: true }),
  zip_code: policy("ZIP code", "contact", { required: true }),
  office: policy("Office", "credentials", {
    required: true,
    owner: "brokerage",
    guidance: "The oNEST office you work from.",
  }),
  license_number: policy("License number", "credentials"),
  license_state: policy("License state", "credentials"),
  license_expires_on: policy("License expiration", "credentials"),
  mls_number: policy("MLS number", "credentials", {
    guidance: "Leave it blank rather than entering a placeholder.",
  }),
  nrds_number: policy("NRDS number", "credentials"),
  bio: policy("Professional bio", "credentials"),
  languages: policy("Languages", "credentials"),
  website_url: policy("Website", "credentials"),
  linkedin_url: policy("LinkedIn", "credentials"),
};

const VALUES: SelfProfileValues = {
  firstName: "Bob",
  lastName: "Lee",
  phoneNumber: "(202) 555-0100",
  streetAddress: "1 Main St",
  city: "Fairfax",
  state: "VA",
  zipCode: "22030",
  officeId: "7",
  mlsNumber: "",
  nrdsNumber: "",
  headshotUrl: null,
  preferredName: "",
  preferredContactMethod: "",
  licenseNumber: "",
  licenseExpiresOn: "",
  licenseState: "",
  bio: "Serving Northern Virginia.",
  websiteUrl: "",
  linkedinUrl: "",
  facebookUrl: "",
  instagramUrl: "",
  xUrl: "",
  languages: [],
  specialties: [],
};

function setPage(
  section: OnboardingProfileSectionCode,
  overrides: Partial<OnboardingPageProps> = {},
) {
  inertia.props = {
    user: {
      id: 1,
      email: "bob@onest.realestate",
      name: "Bob Lee",
      headshotUrl: null,
      permissions: [],
      roles: [],
      roleLabel: "Agent",
      isStaff: false,
      isSuperuser: false,
    },
    csrfToken: "token",
    requestId: "req-1",
    features: {},
    primaryOffice: null,
    notifications: null,
    shell: {
      authorizationVersion: "v1",
      capabilitySchemaVersion: "p0-permissions-v1",
      help: { url: null },
      session: { authenticated: true },
    },
    profileFlow: {
      onboardingVersion: 2,
      currentSection: section,
      sections: [
        {
          code: "identity",
          label: "Identity and photo",
          description: "Confirm who you are and add a professional headshot.",
          status: "in_progress",
          revision: "rev-identity",
        },
        {
          code: "contact",
          label: "Contact and home address",
          description: "How the brokerage reaches you.",
          status: "complete",
          revision: "rev-contact",
        },
        {
          code: "credentials",
          label: "Professional credentials",
          description: "Your office, license, and memberships.",
          status: "not_started",
          revision: "rev-credentials",
        },
        {
          code: "review",
          label: "Review and confirm",
          description: "Check your details exactly as they will be saved.",
          status: null,
          revision: null,
        },
      ],
      fields: FIELDS,
      review: {
        ready: false,
        missing: [{ field: "headshot", label: "Profile photo", section: "identity" }],
        groups: [
          {
            section: "identity",
            label: "Identity and photo",
            rows: [
              {
                field: "headshot",
                label: "Profile photo",
                display: "",
                required: true,
                owner: "agent",
              },
              {
                field: "first_name",
                label: "First name",
                display: "Bob",
                required: true,
                owner: "microsoft",
              },
            ],
          },
          {
            section: "contact",
            label: "Contact and home address",
            rows: [
              {
                field: "phone_number",
                label: "Phone number",
                display: "(202) 555-0100",
                required: true,
                owner: "agent",
              },
              {
                field: "state",
                label: "State",
                display: "Virginia",
                required: true,
                owner: "agent",
              },
            ],
          },
          {
            section: "credentials",
            label: "Professional credentials",
            rows: [
              {
                field: "office",
                label: "Office",
                display: "Mid-Atlantic / Fairfax VA",
                required: true,
                owner: "brokerage",
              },
              {
                field: "mls_number",
                label: "MLS number",
                display: "",
                required: false,
                owner: "agent",
              },
              {
                field: "license_expires_on",
                label: "License expiration",
                display: "June 30, 2030",
                required: false,
                owner: "agent",
              },
            ],
          },
        ],
      },
    },
    identity: {
      email: "bob@onest.realestate",
      emailOwner: "microsoft",
      legalName: { firstName: "Bob", lastName: "Lee" },
      legalNameLocked: true,
      legalNameNotice: null,
    },
    initial: VALUES,
    saved: VALUES,
    validation: { fields: {}, form: [] },
    offices: [{ label: "Mid-Atlantic", offices: [{ id: 7, name: "Fairfax VA" }] }],
    officeLabel: "Mid-Atlantic / Fairfax VA",
    officeSelection: {
      office: {
        id: 7,
        name: "Fairfax VA",
        hierarchy: "ONEST / Mid-Atlantic / Fairfax VA",
        region: "Mid-Atlantic",
        streetAddress: "4000 Chain Bridge Road",
        city: "Fairfax",
        state: "VA",
        zipCode: "22030",
        mainPhone: "(703) 555-0100",
        publicEmail: "fairfax@example.com",
        officeHours: ["Monday–Friday: 9:00 AM–5:00 PM"],
      },
      administrator: {
        id: 22,
        name: "Avery Admin",
        phone: "(703) 555-0199",
        email: "avery@example.com",
        isPrimary: true,
        resolutionLevel: "office",
        resolutionLabel: "Office Branch Admin",
      },
      support: { available: false, message: "" },
    },
    officeConfirmed: true,
    states: [
      { code: "VA", name: "Virginia" },
      { code: "MD", name: "Maryland" },
    ],
    languageOptions: [
      { code: "en", name: "English" },
      { code: "es", name: "Spanish" },
    ],
    contactMethods: [
      { value: "email", label: "Email" },
      { value: "text", label: "Text message" },
    ],
    socialPlatforms: [
      {
        name: "linkedin_url",
        prop: "linkedinUrl",
        label: "LinkedIn",
        placeholder: "https://www.linkedin.com/in/you",
      },
    ],
    limits: {
      headshotMaxBytes: 5 * 1024 * 1024,
      headshotMinDimension: 200,
      bioMaxLength: 1500,
      maxLanguages: 10,
    },
    ...overrides,
  } as OnboardingPageProps;
}

function postedBody(): FormData {
  const call = router.post.mock.calls.at(-1);
  if (!call) {
    throw new Error("Nothing was posted.");
  }
  return call[1] as FormData;
}

function currentOfficeSelection() {
  const selection = inertia.props.officeSelection;
  if (!selection?.administrator) {
    throw new Error("The office-selection fixture requires an administrator.");
  }
  return selection;
}

describe("Onboarding profile flow", () => {
  beforeEach(() => {
    inertia.beforeHandlers = [];
    inertia.remembered = null;
    inertia.rememberSpy.mockReset();
    for (const mock of Object.values(router)) {
      mock.mockReset();
    }
    router.on.mockImplementation((_name: string, handler: BeforeHandler) => {
      inertia.beforeHandlers.push(handler);
      return () => {
        inertia.beforeHandlers = inertia.beforeHandlers.filter(
          (item) => item !== handler,
        );
      };
    });
    transport.uploadHeadshot.mockReset();
    transport.removeHeadshot.mockReset();
    URL.createObjectURL = vi.fn(() => "blob:preview");
    URL.revokeObjectURL = vi.fn();
    setPage("identity");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows Microsoft-owned identity as read-only values, never as controls", () => {
    render(<Onboarding />);
    expect(
      screen.getByRole("heading", { level: 1, name: "Set up your agent profile" }),
    ).toBeVisible();
    expect(screen.getByText("bob@onest.realestate")).toBeInTheDocument();
    expect(screen.getByText("Bob Lee")).toBeInTheDocument();
    expect(screen.getAllByText("Managed by Microsoft")).toHaveLength(2);
    expect(screen.queryByDisplayValue("bob@onest.realestate")).toBeNull();
    expect(screen.queryByLabelText(/^First name/)).toBeNull();
    expect(screen.getByLabelText(/^Preferred name/)).toBeEnabled();
    expect(
      screen.getByText("Only if colleagues call you something else."),
    ).toBeVisible();
  });

  it("lets the agent enter a name Microsoft did not provide", () => {
    setPage("identity", {
      identity: {
        email: "bob@onest.realestate",
        emailOwner: "microsoft",
        legalName: { firstName: "", lastName: "" },
        legalNameLocked: false,
        legalNameNotice: "Microsoft did not send your full name.",
      },
      profileFlow: {
        ...inertia.props.profileFlow,
        fields: {
          ...FIELDS,
          first_name: policy("First name", "identity", { required: true }),
          last_name: policy("Last name", "identity", { required: true }),
        },
      },
    });
    render(<Onboarding />);
    expect(screen.getByText("Microsoft did not send your full name.")).toBeVisible();
    expect(screen.getByLabelText(/^First name/)).toBeRequired();
    expect(screen.getByLabelText(/^Last name/)).toBeRequired();
  });

  it("brings back unsaved values when the agent returns with the browser's Back button", () => {
    inertia.remembered = {
      key: "contact:rev-contact",
      values: { city: ["Typed before Back"], state: ["MD"] },
    };
    setPage("contact");
    render(<Onboarding />);
    expect(screen.getByLabelText(/^City/)).toHaveValue("Typed before Back");
    expect(document.querySelector("input[name='state']")).toHaveValue("MD");
    expect(screen.getByText("Unsaved changes in this section")).toBeInTheDocument();
  });

  it("ignores a remembered draft from an older revision of the section", () => {
    inertia.remembered = { key: "contact:old-revision", values: { city: ["Stale"] } };
    setPage("contact");
    render(<Onboarding />);
    expect(screen.getByLabelText(/^City/)).toHaveValue("Fairfax");
  });

  it("remembers what the agent types so history navigation can restore it", async () => {
    const user = userEvent.setup();
    setPage("contact");
    render(<Onboarding />);
    await user.type(screen.getByLabelText(/^City/), "x");
    expect(inertia.rememberSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({
        key: "contact:rev-contact",
        values: expect.objectContaining({ city: ["Fairfaxx"] }),
      }),
    );
  });

  it("posts a section through Inertia with its concurrency tokens, exactly once", async () => {
    const user = userEvent.setup();
    render(<Onboarding />);
    await user.type(screen.getByLabelText(/^Preferred name/), "Bobby");

    const save = screen.getByRole("button", { name: /Save and continue/ });
    await user.click(save);
    await user.click(save);

    expect(router.post).toHaveBeenCalledTimes(1);
    expect(router.post).toHaveBeenCalledWith(
      "/onboarding/profile/sections/identity",
      expect.any(FormData),
      expect.objectContaining({ preserveScroll: true }),
    );
    const body = postedBody();
    expect(body.get("revision")).toBe("rev-identity");
    expect(body.get("expected_onboarding_version")).toBe("2");
    expect(body.get("csrfmiddlewaretoken")).toBe("token");
    expect(body.get("preferred_name")).toBe("Bobby");
    expect(body.has("first_name")).toBe(false);
    expect(screen.getByRole("button", { name: /Saving/ })).toBeDisabled();
  });

  it("keeps typed values and the section after a 422, then focuses the first invalid field", () => {
    setPage("contact", {
      initial: { ...VALUES, phoneNumber: "123", city: "Kept" },
      validation: {
        fields: { phone_number: ["Enter a valid US phone number."] },
        form: [],
      },
    });
    render(<Onboarding />);

    const phone = screen.getByLabelText(/^Phone number/);
    expect(phone).toHaveValue("123");
    expect(screen.getByLabelText(/^City/)).toHaveValue("Kept");
    expect(phone).toHaveAttribute("aria-invalid", "true");
    expect(phone).toHaveFocus();
    const summary = screen.getByRole("alert", { name: "Check the highlighted fields" });
    expect(within(summary).getByRole("link", { name: /Phone number/ })).toHaveAttribute(
      "href",
      "#phone_number",
    );
    expect(screen.getByText("Unsaved changes in this section")).toBeInTheDocument();
  });

  it("moves focus to the summary when the problem is not tied to one field", () => {
    setPage("contact", {
      validation: {
        fields: {},
        form: [
          "This section was changed in another tab or window since you opened it.",
        ],
      },
    });
    render(<Onboarding />);
    expect(screen.getByText(/changed in another tab/)).toBeVisible();
    expect(document.activeElement).toContainElement(
      screen.getByText(/changed in another tab/),
    );
  });

  it("navigates between sections with Inertia visits that keep the section in the URL", async () => {
    const user = userEvent.setup();
    render(<Onboarding />);
    await user.click(screen.getByRole("button", { name: /Contact and home address/ }));
    expect(router.get).toHaveBeenCalledWith("/onboarding", { section: "contact" });
  });

  it("gives every step an accessible name that carries its position and status", () => {
    render(<Onboarding />);
    const nav = screen.getByRole("navigation", { name: "Profile setup steps" });
    const steps = within(nav).getAllByRole("button");
    expect(steps).toHaveLength(4);
    expect(steps[0]).toHaveAttribute("aria-current", "step");
    expect(steps[0]).toHaveAccessibleName(/step 1 of 4, in progress/);
    expect(steps[1]).toHaveAccessibleName(/step 2 of 4, complete/);
    // On a phone only the current label is drawn; the others stay announced.
    expect(within(steps[1]).getByText("Contact and home address")).toHaveClass(
      "max-sm:sr-only",
    );
  });

  it("holds a navigation away from unsaved edits until the agent decides", async () => {
    const user = userEvent.setup();
    setPage("contact");
    render(<Onboarding />);
    await user.type(screen.getByLabelText(/^City/), "x");

    const handler = inertia.beforeHandlers.at(-1);
    expect(handler).toBeDefined();
    const url = new URL("http://localhost/onboarding?section=identity");
    // A partial reload (after a photo upload) is never held.
    expect(
      handler?.({ detail: { visit: { method: "get", only: ["profileFlow"], url } } }),
    ).toBeUndefined();

    let result: boolean | undefined;
    act(() => {
      result = handler?.({ detail: { visit: { method: "get", only: [], url } } });
    });
    expect(result).toBe(false);
    expect(
      await screen.findByRole("dialog", { name: "Leave this section without saving?" }),
    ).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Discard changes" }));
    expect(router.visit).toHaveBeenCalledWith(url.href, expect.any(Object));
  });

  it("keeps the public introduction collapsed without dropping its values", async () => {
    const user = userEvent.setup();
    setPage("credentials", {
      initial: { ...VALUES, bio: "" },
      saved: { ...VALUES, bio: "" },
    });
    render(<Onboarding />);

    const toggle = screen.getByRole("button", { name: /Public introduction/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(document.getElementById("credentials-introduction")).not.toBeVisible();
    expect(screen.getByText(/placeholder/)).toBeVisible();
    expect(screen.getByText("Managed by oNEST")).toBeVisible();

    await user.click(screen.getByRole("button", { name: /Save and continue/ }));
    expect(postedBody().has("bio")).toBe(true);
    expect(postedBody().get("office")).toBe("7");
    expect(postedBody().get("confirm_office")).toBe("true");
    expect(postedBody().get("confirmed_office_id")).toBe("7");
  });

  it("shows the selected office, its public address, and current administrator", () => {
    setPage("credentials");
    render(<Onboarding />);

    expect(screen.getByRole("heading", { name: "Fairfax VA" })).toBeVisible();
    expect(screen.getByText("Office address")).toBeVisible();
    expect(screen.getByText(/4000 Chain Bridge Road/)).toBeVisible();
    expect(screen.getByText("Avery Admin")).toBeVisible();
    expect(screen.getByRole("link", { name: "Call Avery Admin" })).toHaveAttribute(
      "href",
      "tel:7035550199",
    );
    expect(screen.getByRole("link", { name: "Email Avery Admin" })).toHaveAttribute(
      "href",
      "mailto:avery@example.com",
    );
    expect(screen.getByText(/never changes the home or mailing address/)).toBeVisible();
  });

  it("shows an honest support path when no current office administrator exists", () => {
    const selection = currentOfficeSelection();
    setPage("credentials", {
      officeSelection: {
        ...selection,
        administrator: null,
        support: {
          available: true,
          message: "No current office administrator is available. Contact IT Support.",
        },
      },
    });
    render(<Onboarding />);

    expect(screen.getByText("Office administrator unavailable")).toBeVisible();
    expect(screen.getByText(/Contact IT Support/)).toBeVisible();
    expect(screen.queryByText(/We notified/)).not.toBeInTheDocument();
  });

  it("invalidates confirmation and loads only the newly selected office", async () => {
    const user = userEvent.setup();
    const selection = currentOfficeSelection();
    const nextSelection = {
      ...selection,
      office: {
        ...selection.office,
        id: 8,
        name: "Baltimore",
        city: "Baltimore",
      },
      administrator: {
        ...selection.administrator,
        id: 23,
        name: "Blair Admin",
        email: "blair@example.com",
      },
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(nextSelection), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    setPage("credentials", {
      offices: [
        {
          label: "Mid-Atlantic",
          offices: [
            { id: 7, name: "Fairfax VA" },
            { id: 8, name: "Baltimore" },
          ],
        },
      ],
    });
    render(<Onboarding />);

    await user.click(screen.getByLabelText(/^Office/));
    await user.click(screen.getByRole("option", { name: "Baltimore" }));

    expect(await screen.findByRole("heading", { name: "Baltimore" })).toBeVisible();
    expect(screen.getByText("Blair Admin")).toBeVisible();
    const confirmation = screen.getByRole("checkbox", {
      name: /I confirm this is the office/,
    });
    expect(confirmation).not.toBeChecked();
    await user.click(confirmation);
    await user.click(screen.getByRole("button", { name: /Save and continue/ }));
    expect(postedBody().get("office")).toBe("8");
    expect(postedBody().get("confirm_office")).toBe("true");
    expect(postedBody().get("confirmed_office_id")).toBe("8");
  });

  it("opens the introduction when the server rejects a value inside it", () => {
    setPage("credentials", {
      validation: { fields: { linkedin_url: ["Enter a LinkedIn address."] }, form: [] },
    });
    render(<Onboarding />);
    expect(screen.getByRole("button", { name: /Public introduction/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByLabelText(/^LinkedIn/)).toHaveFocus();
  });

  it("keeps typed text when an upload fails, and retries into a saved photo", async () => {
    const user = userEvent.setup();
    render(<Onboarding />);
    await user.type(screen.getByLabelText(/^Preferred name/), "Bobby");

    transport.uploadHeadshot.mockRejectedValueOnce(
      new HeadshotRequestError("Photo storage is unavailable right now.", {
        retryable: true,
      }),
    );
    const file = new File(["jpeg"], "me.jpg", { type: "image/jpeg" });
    await user.upload(screen.getByLabelText("Choose file for Upload headshot"), file);

    expect(
      await screen.findByText("Photo storage is unavailable right now."),
    ).toBeVisible();
    expect(screen.getByLabelText(/^Preferred name/)).toHaveValue("Bobby");
    expect(router.reload).not.toHaveBeenCalled();

    transport.uploadHeadshot.mockResolvedValueOnce(
      "http://testserver/account/headshot/file?v=1",
    );
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Photo saved")).toBeVisible();
    expect(router.reload).toHaveBeenCalledWith({
      only: ["profileFlow", "saved", "user"],
    });
    expect(screen.getByLabelText(/^Preferred name/)).toHaveValue("Bobby");
  });

  it("offers to sign in again when the session expired mid-upload", async () => {
    const user = userEvent.setup();
    render(<Onboarding />);
    transport.uploadHeadshot.mockRejectedValueOnce(
      new HeadshotRequestError("Your session expired.", { sessionExpired: true }),
    );
    await user.upload(
      screen.getByLabelText("Choose file for Upload headshot"),
      new File(["jpeg"], "me.jpg", { type: "image/jpeg" }),
    );
    expect(await screen.findByRole("link", { name: "Sign in again" })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("removes a photo before finishing, and says one is required", async () => {
    const user = userEvent.setup();
    setPage("identity", {
      initial: {
        ...VALUES,
        headshotUrl: "http://testserver/account/headshot/file?v=1",
      },
    });
    transport.removeHeadshot.mockResolvedValueOnce(undefined);
    render(<Onboarding />);

    expect(screen.getByText("Photo saved")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Remove photo" }));
    expect(await screen.findByText("Photo required")).toBeVisible();
    expect(transport.removeHeadshot).toHaveBeenCalledWith({ csrfToken: "token" });
  });

  it("reviews the saved values and sends the agent back to edit any section", async () => {
    const user = userEvent.setup();
    setPage("review");
    render(<Onboarding />);

    expect(screen.getByText("(202) 555-0100")).toBeVisible();
    expect(screen.getByText("June 30, 2030")).toBeVisible();
    expect(screen.getByText("Missing")).toBeVisible();
    expect(screen.getByText("Not provided")).toBeVisible();

    await user.click(
      screen.getByRole("button", { name: "Edit Contact and home address" }),
    );
    expect(router.get).toHaveBeenCalledWith("/onboarding", { section: "contact" });

    await user.click(screen.getByRole("button", { name: /Profile photo: Required/ }));
    expect(router.get).toHaveBeenCalledWith("/onboarding", { section: "identity" });
  });

  it("finishes with an explicit confirmation through the finalize endpoint", async () => {
    const user = userEvent.setup();
    setPage("review");
    render(<Onboarding />);

    await user.click(screen.getByRole("checkbox", { name: /I confirm these details/ }));
    await user.click(screen.getByRole("button", { name: /Finish setup/ }));

    expect(router.post).toHaveBeenCalledWith(
      "/onboarding/profile/finalize",
      expect.any(FormData),
      expect.any(Object),
    );
    expect(postedBody().get("confirm_review")).toBe("true");
    expect(postedBody().get("expected_onboarding_version")).toBe("2");
  });

  it("lists finish errors from the server with a way back to each section", async () => {
    const user = userEvent.setup();
    setPage("review", {
      validation: {
        fields: {
          office: ["That office is no longer available."],
          confirm_review: ["Confirm that these details are correct before you finish."],
        },
        form: [],
      },
    });
    render(<Onboarding />);

    expect(screen.getByRole("checkbox", { name: /I confirm/ })).toHaveFocus();
    await user.click(
      screen.getByRole("button", {
        name: /Office: That office is no longer available/,
      }),
    );
    expect(router.get).toHaveBeenCalledWith("/onboarding", { section: "credentials" });
  });

  it("keeps a working sign-out action on every section", async () => {
    const user = userEvent.setup();
    render(<Onboarding />);
    await user.click(screen.getByRole("button", { name: "Sign out" }));
    expect(router.post).toHaveBeenCalledWith("/logout");
  });

  it("moves through the editable fields in order with the keyboard", async () => {
    const user = userEvent.setup();
    setPage("contact");
    render(<Onboarding />);
    screen.getByLabelText(/^Phone number/).focus();
    await user.tab();
    expect(screen.getByRole("radio", { name: "No preference" })).toHaveFocus();
  });

  it.each(["identity", "contact", "credentials", "review"] as const)(
    "has no detectable accessibility violations on %s",
    async (section) => {
      setPage(section);
      const { container } = render(<Onboarding />);
      expect(await axe(container)).toHaveNoViolations();
    },
  );
});
