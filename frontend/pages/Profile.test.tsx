import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { formatFormDate } from "@/lib/dates";
import Profile from "@/pages/Profile";
import type { ProfilePageProps, SelfProfileValues } from "@/types";
import type { ValidationErrors } from "@/types/design-system";

const pageProps = vi.hoisted(() => ({ current: {} as ProfilePageProps }));
const routerPost = vi.hoisted(() =>
  vi.fn((_url: string, _data: unknown, options?: { onFinish?: () => void }) => {
    options?.onFinish?.();
  }),
);

vi.mock("@inertiajs/react", () => ({
  usePage: () => ({ props: pageProps.current, url: "/profile" }),
  Head: () => null,
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
  router: { post: routerPost, reload: vi.fn() },
}));

const emptyValidation: ValidationErrors = { fields: {}, form: [] };

const initial: SelfProfileValues = {
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
  preferredName: "Bobby",
  preferredContactMethod: "text",
  licenseNumber: "VA-9911",
  licenseState: "VA",
  licenseExpiresOn: "2030-06-30",
  bio: "Hello",
  websiteUrl: "https://bobsells.example.com",
  linkedinUrl: "",
  facebookUrl: "",
  instagramUrl: "",
  xUrl: "",
  languages: ["en"],
  specialties: ["residential"],
  headshotUrl: null,
};

function setPage(overrides: Partial<ProfilePageProps> = {}) {
  pageProps.current = {
    user: {
      id: 1,
      email: "bob@onest.realestate",
      name: "Bob Lee",
      headshotUrl: null,
      permissions: [],
      roles: ["Realtor"],
      roleLabel: "Realtor",
      isStaff: false,
      isSuperuser: false,
    },
    csrfToken: "token",
    requestId: "req-1",
    features: {},
    primaryOffice: null,
    shell: {
      authorizationVersion: "v1",
      capabilitySchemaVersion: "p0-permissions-v1",
      help: { url: "https://help.example.com" },
      session: { authenticated: true },
    },
    notifications: null,
    initial,
    validation: emptyValidation,
    offices: [{ label: "Mid-Atlantic", offices: [{ id: 7, name: "Fairfax VA" }] }],
    states: [
      { code: "VA", name: "Virginia" },
      { code: "MD", name: "Maryland" },
    ],
    languageOptions: [
      { code: "en", name: "English" },
      { code: "es", name: "Spanish" },
    ],
    specialtyOptions: [
      { code: "residential", name: "Residential" },
      { code: "commercial", name: "Commercial" },
    ],
    contactMethods: [
      { value: "email", label: "Email" },
      { value: "phone", label: "Phone call" },
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
    identity: {
      email: "bob@onest.realestate",
      legalName: "Bob Lee",
      displayName: "Bob Lee",
      preferredDisplayName: "Bobby",
      roles: ["Realtor"],
      office: {
        id: 7,
        name: "Fairfax VA",
        pathLabel: "Mid-Atlantic / Virginia / Fairfax VA",
        regionName: "Mid-Atlantic",
        streetAddress: "2 Office Way",
        city: "Fairfax",
        state: "VA",
        zipCode: "22030",
        mainPhone: "(703) 555-0100",
      },
      accountStatus: "active",
      isStaff: false,
      memberSince: "2024-02-01T00:00:00+00:00",
      onboardingCompletedAt: "2024-02-02T00:00:00+00:00",
      licenseStatus: { state: "current", days: 400, tone: "success" },
      administrative: {
        // Deliberately not "Active": the account-status badge above already
        // uses that word, and the assertions below rely on unique text.
        agentStatus: { value: "on_leave", label: "On leave", tone: "warning" },
        startDate: "2024-02-01",
        agentIdentifier: "ON-4412",
        licenseVerification: {
          state: "verified",
          label: "Verified",
          tone: "success",
          verifiedAt: "2024-03-01T00:00:00+00:00",
          verifiedBy: "Ada Admin",
          note: "Checked against the VA DPOR record.",
        },
        contractStatus: {
          status: null,
          label: "Not connected",
          tone: "neutral",
          source: "contract",
          available: false,
          reason: "Agent contracts are not connected to the hub yet.",
        },
        lastReviewedAt: "2024-03-01T00:00:00+00:00",
      },
    },
    editable: { office: true },
    completeness: {
      completed: 15,
      total: 20,
      percent: 79,
      missing: [
        {
          key: "mls_number",
          label: "MLS number",
          section: "credentials",
          sectionLabel: "Office and credentials",
          required: false,
        },
      ],
    },
    limits: {
      headshotMaxBytes: 5 * 1024 * 1024,
      headshotMinDimension: 200,
      bioMaxLength: 1500,
      maxLanguages: 10,
      maxSpecialties: 8,
    },
    ...overrides,
  } as ProfilePageProps;
}

describe("Profile", () => {
  /** Open a profile tab the way a reader does — by its tab. */
  async function openTab(user: ReturnType<typeof userEvent.setup>, name: string) {
    await user.click(screen.getByRole("tab", { name }));
  }

  beforeEach(() => {
    window.history.replaceState({}, "", "/profile");
    setPage();
    routerPost.mockReset();
    routerPost.mockImplementation(
      (_url: string, _data: unknown, options?: { onFinish?: () => void }) => {
        options?.onFinish?.();
      },
    );
  });

  it("posts to the self-service endpoint via Inertia FormData", async () => {
    const user = userEvent.setup();
    const { container } = render(<Profile />);
    const form = container.querySelector("form");
    expect(form).toHaveAttribute("action", "/profile/submit");
    expect(form).toHaveAttribute("method", "post");
    expect(container.querySelector("input[name='csrfmiddlewaretoken']")).toHaveValue(
      "token",
    );

    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(routerPost).toHaveBeenCalledWith(
      "/profile/submit",
      expect.any(FormData),
      expect.objectContaining({ preserveScroll: true }),
    );
    const body = routerPost.mock.calls[0][1] as FormData;
    expect(body.get("csrfmiddlewaretoken")).toBe("token");
    expect(body.get("preferred_name")).toBe("Bobby");
  });

  it("pre-fills every self-editable field from the server payload", () => {
    render(<Profile />);
    expect(screen.getByLabelText(/^First name/)).toHaveValue("Bob");
    expect(screen.getByLabelText(/^Preferred name/)).toHaveValue("Bobby");
    expect(screen.getByLabelText(/^License number/)).toHaveValue("VA-9911");
    expect(document.querySelector("input[name='license_expires_on']")).toHaveValue(
      "2030-06-30",
    );
    expect(screen.getByLabelText(/^License expiration/)).toHaveTextContent(
      formatFormDate("2030-06-30"),
    );
    expect(screen.getByLabelText(/^Professional bio/)).toHaveValue("Hello");
    expect(screen.getByLabelText(/^Website/, { selector: "input" })).toHaveValue(
      "https://bobsells.example.com",
    );
  });

  it("renders Microsoft identity and roles as read-only values, not inputs", async () => {
    const user = userEvent.setup();
    render(<Profile />);
    await openTab(user, "Account");
    expect(screen.getByRole("heading", { name: "Account details" })).toBeVisible();
    const account = screen.getByRole("tabpanel", { name: "Account" });
    expect(within(account).getByText("bob@onest.realestate")).toBeInTheDocument();
    expect(within(account).getByText("Realtor")).toBeInTheDocument();
    expect(within(account).getByText("Active")).toBeInTheDocument();
    // Read-only means no control at all — not a disabled one the user can focus.
    expect(screen.queryByLabelText(/work email/i)).toBeNull();
    expect(screen.queryByDisplayValue("bob@onest.realestate")).toBeNull();
    expect(screen.queryByDisplayValue("Realtor")).toBeNull();
  });

  it("shows the brokerage record as read-only facts, never as controls", async () => {
    const user = userEvent.setup();
    render(<Profile />);
    await openTab(user, "Account");
    expect(screen.getByRole("heading", { name: "Brokerage record" })).toBeVisible();
    expect(screen.getByText("On leave")).toBeInTheDocument();
    expect(screen.getByText("ON-4412")).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByText("Not connected")).toBeInTheDocument();
    // No control means the value cannot be submitted back; the server rejects
    // the field names outright as well.
    expect(screen.queryByLabelText(/agent status/i)).toBeNull();
    expect(screen.queryByLabelText(/agent id/i)).toBeNull();
    expect(screen.queryByDisplayValue("ON-4412")).toBeNull();
  });

  it("never renders the brokerage's operational notes", () => {
    const { container } = render(<Profile />);
    // The prop does not exist on the payload at all — assert on the rendered
    // document so a future panel cannot start printing one.
    expect(container.textContent).not.toMatch(/operational notes/i);
  });

  it("never offers a password or local login control", () => {
    const { container } = render(<Profile />);
    expect(container.querySelector("input[type='password']")).toBeNull();
    expect(screen.queryByText(/password/i)).toBeNull();
  });

  it("submits the selected office when the user may change it", () => {
    const { container } = render(<Profile />);
    expect(container.querySelector("input[name='office']")).toHaveValue("7");
  });

  it("explains a locked office instead of submitting one", () => {
    setPage({ editable: { office: false }, offices: [] });
    const { container } = render(<Profile />);
    expect(container.querySelector("input[name='office']")).toBeNull();
    expect(screen.getByText(/administrator\s+has to move it/i)).toBeInTheDocument();
    expect(
      screen.getByText("Mid-Atlantic / Virginia / Fairfax VA"),
    ).toBeInTheDocument();
  });

  it("points at support for the values it cannot change", async () => {
    const user = userEvent.setup();
    render(<Profile />);
    await openTab(user, "Account");
    expect(
      screen.getByRole("link", { name: "Open a support request" }),
    ).toHaveAttribute("href", "https://help.example.com");
  });

  it("falls back to plain guidance when no help destination is configured", () => {
    setPage({
      shell: {
        authorizationVersion: "v1",
        capabilitySchemaVersion: "p0-permissions-v1",
        help: { url: null },
        session: { authenticated: true },
      },
    });
    render(<Profile />);
    expect(screen.queryByRole("link", { name: /support request/i })).toBeNull();
    expect(screen.getByText("Contact your office administrator.")).toBeInTheDocument();
  });

  it("keeps submitted values and surfaces field and summary errors after a 422", () => {
    setPage({
      initial: { ...initial, zipCode: "nope", preferredName: "Kept" },
      validation: {
        fields: { zip_code: ["Enter a 5-digit ZIP code."] },
        form: [],
      },
    });
    render(<Profile />);
    expect(screen.getByLabelText(/^ZIP/)).toHaveValue("nope");
    expect(screen.getByLabelText(/^Preferred name/)).toHaveValue("Kept");
    expect(screen.getByLabelText(/^ZIP/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText(/^ZIP/)).toHaveAttribute(
      "aria-describedby",
      "zip_code_error",
    );
    const summary = screen.getByRole("alert", {
      name: "Check the highlighted fields",
    });
    expect(within(summary).getByRole("link", { name: /ZIP code/ })).toHaveAttribute(
      "href",
      "#zip_code",
    );
  });

  it("tracks unsaved changes and posts through Inertia without a full refresh", async () => {
    const user = userEvent.setup();
    // Hold the visit open so the Saving… state is observable.
    routerPost.mockImplementationOnce(() => undefined);
    render(<Profile />);

    expect(screen.getByText("All changes saved.")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/^Preferred name/), "!");
    expect(screen.getByText("You have unsaved changes.")).toBeInTheDocument();

    const save = screen.getByRole("button", { name: "Save changes" });
    await user.click(save);
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(routerPost).toHaveBeenCalledWith(
      "/profile/submit",
      expect.any(FormData),
      expect.objectContaining({ preserveScroll: true }),
    );
  });

  it("keeps the language selection in hidden inputs the form can post", async () => {
    const user = userEvent.setup();
    const { container } = render(<Profile />);
    await openTab(user, "Professional");
    const posted = () =>
      Array.from(
        container.querySelectorAll<HTMLInputElement>("input[name='languages']"),
      ).map((input) => input.value);

    expect(posted()).toEqual(["en"]);
    await user.click(screen.getByRole("checkbox", { name: "Spanish" }));
    expect(posted()).toEqual(["en", "es"]);
    await user.click(screen.getByRole("checkbox", { name: "English" }));
    expect(posted()).toEqual(["es"]);
  });

  it("stops the user adding more languages than the server accepts", async () => {
    const user = userEvent.setup();
    setPage({ limits: { ...pageProps.current.limits, maxLanguages: 1 } });
    render(<Profile />);
    await openTab(user, "Professional");
    expect(screen.getByRole("checkbox", { name: "Spanish" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: "English" }));
    expect(screen.getByRole("checkbox", { name: "Spanish" })).toBeEnabled();
  });

  it("counts bio characters against the server limit", async () => {
    const user = userEvent.setup();
    render(<Profile />);
    expect(screen.getByText("5 of 1500 characters used.")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/^Professional bio/), "!");
    expect(screen.getByText("6 of 1500 characters used.")).toBeInTheDocument();
  });

  it("says what is missing and takes the reader to it", async () => {
    const user = userEvent.setup();
    render(<Profile />);
    expect(screen.getByText(/Still to add: MLS number/)).toBeVisible();
    expect(screen.getByText("15 of 20 details")).toBeVisible();

    await user.click(screen.getByRole("button", { name: /Add mls number/i }));
    expect(screen.getByRole("tab", { name: "Professional" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(window.location.hash).toBe("#professional");
  });

  it("keeps every tab's fields in the form so Save posts the whole profile", async () => {
    const user = userEvent.setup();
    render(<Profile />);
    // Professional is not showing, yet its values still travel.
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    const body = routerPost.mock.calls[0][1] as FormData;
    expect(body.get("license_number")).toBe("VA-9911");
    expect(body.get("first_name")).toBe("Bob");
  });

  it("opens the tab holding the error after a refused save", () => {
    setPage({
      validation: { fields: { license_number: ["Required."] }, form: [] },
    });
    render(<Profile />);
    const professional = screen.getByRole("tab", { name: /Professional/ });
    expect(professional).toHaveAttribute("aria-selected", "true");
    expect(professional).toHaveTextContent("1");
  });

  it("moves between tabs with the arrow keys", async () => {
    const user = userEvent.setup();
    render(<Profile />);
    screen.getByRole("tab", { name: "Personal" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Professional" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "Professional" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("is reachable by keyboard through the editable fields in order", async () => {
    const user = userEvent.setup();
    render(<Profile />);
    screen.getByLabelText(/^First name/).focus();
    await user.tab();
    expect(screen.getByLabelText(/^Last name/)).toHaveFocus();
    await user.tab();
    expect(screen.getByLabelText(/^Preferred name/)).toHaveFocus();
  });

  it("has no detectable accessibility violations", async () => {
    const { container } = render(<Profile />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
