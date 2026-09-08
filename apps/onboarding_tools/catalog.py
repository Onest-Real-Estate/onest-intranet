"""The seeded tool catalog.

Data, not code: this module is the *initial* content a migration writes, and
every row is editable afterwards without a deploy. It lives here rather than
inline in the migration so the list stays readable and reviewable — a migration
is the wrong place to argue about what SmartMLS is for.

Guides are the point. Each row either carries steps an agent can follow now, or
names who at oNEST turns the account on, because a checklist that says "you need
HiHello" without saying how to get it has moved the problem rather than solved
it. A database constraint refuses a row with neither.
"""

from __future__ import annotations

#: Offices an association or MLS row attaches to, by office slug. Resolution
#: walks the tree, so naming a state node covers every branch beneath it.
#: A slug that does not exist in this deployment is skipped rather than failing
#: the migration — the seed must not depend on one brokerage's office tree.
CONNECTICUT = ("connecticut",)

COMPANY_TOOLS: tuple[dict, ...] = (
    {
        "slug": "skyslope",
        "name": "SkySlope",
        "description": "Transaction documents, signatures, and compliance files.",
        "provisioning": "onest",
        "contact_label": "IT support — raise a request and we create the seat",
        "setup_steps": [],
    },
    {
        "slug": "lofty",
        "name": "Lofty",
        "description": "CRM, lead follow-up, campaigns, and your agent pipeline.",
        "provisioning": "onest",
        "contact_label": "IT support — we create the seat and assign your lead routing",
        "setup_steps": [],
    },
    {
        "slug": "office-365",
        "name": "Office 365",
        "description": "Company email, calendar, Word, Excel, and Teams access.",
        "provisioning": "onest",
        "contact_label": "IT support — created with your oNEST account",
        "setup_steps": [],
    },
    {
        "slug": "onedrive",
        "name": "OneDrive",
        "description": "Secure cloud storage for your personal work files.",
        "provisioning": "self_serve",
        "setup_steps": [
            "Sign in at office.com with your oNEST email.",
            "Open the app launcher and choose OneDrive.",
            "Install the desktop app so your files sync offline.",
        ],
        "contact_label": "IT support, if sign-in fails",
    },
    {
        "slug": "sharepoint",
        "name": "SharePoint",
        "description": "Shared company documents and internal team resources.",
        "provisioning": "self_serve",
        "setup_steps": [
            "Sign in at office.com with your oNEST email.",
            "Open the app launcher and choose SharePoint.",
            "Follow the oNEST company site so it appears on your home page.",
        ],
        "contact_label": "IT support, if you cannot see the company site",
    },
    {
        "slug": "closely",
        "name": "Closely",
        "description": "Outreach and marketing automation workspace.",
        "provisioning": "onest",
        "contact_label": "Marketing — they issue Closely seats",
        "setup_steps": [],
    },
    {
        "slug": "rpr",
        "name": "RPR",
        "description": "Property research, reports, and market analytics.",
        "provisioning": "self_serve",
        "setup_steps": [
            "Go to narrpr.com and choose Create Account.",
            "Verify with your NRDS number — your association can supply it.",
            "Confirm the email RPR sends you.",
        ],
        "contact_label": "Your branch admin, for your NRDS number",
        "help_url": "https://blog.narrpr.com/support/",
    },
    {
        "slug": "kv-agent-one",
        "name": "KV Agent One",
        "description": "Agent site and lead capture platform.",
        "provisioning": "both",
        "setup_steps": [
            "Request your site at the link above.",
            "Choose your subdomain and upload a headshot and bio.",
            "Tell IT once it is live so we can point leads at it.",
        ],
        "contact_label": "Marketing — they approve the site before it goes live",
    },
    {
        "slug": "agentfusion",
        "name": "AgentFusion",
        "description": (
            "AI-powered workspace for agent productivity and client service."
        ),
        "provisioning": "onest",
        "contact_label": "IT support — seats are issued per office",
        "setup_steps": [],
    },
)

ASSOCIATION_TOOLS: tuple[dict, ...] = (
    {
        "slug": "c2ex",
        "name": "C2EX",
        "description": "NAR professional endorsement and learning program.",
        "provisioning": "self_serve",
        "setup_steps": [
            "Sign in at c2ex.realtor with your NAR login.",
            "Take the self-assessment to get your starting score.",
            "Work through the recommended learning path.",
        ],
        "contact_label": "Your branch admin, if your NAR login does not work",
    },
    {
        "slug": "ct-realtors",
        "name": "CT Realtors",
        "description": "Connecticut association access and member resources.",
        "provisioning": "both",
        "offices": CONNECTICUT,
        "setup_steps": [
            "Join through your local board — your branch admin will say which.",
            "Pay the member dues invoice they send you.",
            "Send your member number to IT so we can link your MLS access.",
        ],
        "contact_label": "Your branch admin — they sponsor your membership",
    },
    {
        "slug": "smartmls",
        "name": "SmartMLS",
        "description": "MLS listings, data, and market tools.",
        "provisioning": "both",
        "offices": CONNECTICUT,
        "setup_steps": [
            "Your association membership must be active first.",
            "Complete SmartMLS onboarding when they email you.",
            "Send IT your MLS ID so we can connect Lofty and SkySlope.",
        ],
        "contact_label": "Your branch admin, then IT support to link the tools",
    },
    {
        "slug": "showingtime",
        "name": "ShowingTime",
        "description": "Showing requests, confirmations, and feedback.",
        "provisioning": "self_serve",
        "offices": CONNECTICUT,
        "setup_steps": [
            "Sign in with your SmartMLS credentials — no separate account.",
            "Set your showing notification preferences.",
            "Add your mobile number so confirmations reach you.",
        ],
        "contact_label": "IT support, if sign-in fails",
    },
    {
        "slug": "sentrilock",
        "name": "SentriLock",
        "description": "Lockbox access and showing security.",
        "provisioning": "both",
        "offices": CONNECTICUT,
        "setup_steps": [
            "Your association issues the SentriLock card or app licence.",
            "Install the SentriKey app and sign in.",
            "Test on an office lockbox before your first showing.",
        ],
        "contact_label": "Your branch admin — they order the card",
    },
    {
        "slug": "internal-chatbot",
        "name": "Internal Chatbot",
        "description": "Internal answers and a support reference point.",
        "provisioning": "self_serve",
        "setup_steps": ["Open it from the hub — your oNEST login is all it needs."],
        "contact_label": "IT support",
    },
    {
        "slug": "training-portal",
        "name": "Training Portal",
        "description": "Required training and your onboarding learning path.",
        "provisioning": "self_serve",
        "setup_steps": [
            "Open it from the hub with your oNEST login.",
            "Start the New Agent path — it is assigned automatically.",
        ],
        "contact_label": "Your branch admin, for training questions",
    },
)

MARKETING_TOOLS: tuple[dict, ...] = (
    {
        "slug": "homes-com",
        "name": "Homes.com",
        "description": "Consumer-facing agent profile and listings presence.",
        "provisioning": "self_serve",
        "setup_steps": [
            "Claim your profile at homes.com using your licence details.",
            "Add your headshot, bio, and oNEST office address.",
            "Link your MLS ID so your listings appear.",
        ],
        "contact_label": "Marketing, for approved bio and photo",
    },
    {
        "slug": "hihello",
        "name": "HiHello",
        "description": "Digital business card and QR contact sharing.",
        "provisioning": "self_serve",
        "setup_steps": [
            "Download HiHello and sign up with your oNEST email.",
            "Use the oNEST card template Marketing publishes.",
            "Add your QR code to your email signature.",
        ],
        "contact_label": "Marketing, for the oNEST card template",
    },
    {
        "slug": "google-business",
        "name": "Google Business",
        "description": "Public business profile for search and maps.",
        "provisioning": "both",
        "setup_steps": [
            "Ask Marketing to add you to the oNEST business profile.",
            "Accept the invitation Google emails you.",
            "Keep your hours and contact details current.",
        ],
        "contact_label": "Marketing — they own the business profile",
    },
    {
        "slug": "facebook",
        "name": "Facebook",
        "description": "Social profile or business page setup.",
        "provisioning": "self_serve",
        "is_required": False,
        "setup_steps": [
            "Create a business page separate from your personal profile.",
            "Use the oNEST brand assets Marketing publishes.",
            "Add your page link to your agent profile.",
        ],
        "contact_label": "Marketing, for brand assets",
    },
    {
        "slug": "instagram",
        "name": "Instagram",
        "description": "Visual social profile for agent marketing.",
        "provisioning": "self_serve",
        "is_required": False,
        "setup_steps": [
            "Create a professional account, not a personal one.",
            "Use the oNEST bio and link format Marketing publishes.",
            "Connect it to your Facebook business page.",
        ],
        "contact_label": "Marketing, for brand assets",
    },
    {
        "slug": "realtor-com",
        "name": "Realtor.com",
        "description": "Agent profile and listing visibility.",
        "provisioning": "self_serve",
        "setup_steps": [
            "Claim your profile at realtor.com/realestateagents.",
            "Verify with your NRDS number.",
            "Add your headshot, bio, and office address.",
        ],
        "contact_label": "Your branch admin, for your NRDS number",
    },
    {
        "slug": "zillow",
        "name": "Zillow",
        "description": "Agent profile, reviews, and listing presence.",
        "provisioning": "self_serve",
        "setup_steps": [
            "Create an agent account at zillow.com/agent-resources.",
            "Claim your listings and set your service areas.",
            "Ask past clients for reviews — they carry most of the weight.",
        ],
        "contact_label": "Marketing, for approved bio and photo",
    },
)


def seed_rows() -> list[dict]:
    """Every catalog row, stamped with its group and display order."""
    rows: list[dict] = []
    for group, tools in (
        ("company", COMPANY_TOOLS),
        ("association", ASSOCIATION_TOOLS),
        ("marketing", MARKETING_TOOLS),
    ):
        for index, tool in enumerate(tools):
            row = dict(tool)
            row["group"] = group
            row["sort_order"] = index * 10
            rows.append(row)
    return rows
