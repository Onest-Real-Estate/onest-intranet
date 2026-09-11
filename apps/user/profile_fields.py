"""Professional-profile vocabulary and normalizers.

Everything an agent may maintain about themselves beyond the onboarding
essentials lives here: the closed sets we accept (languages, contact methods,
social platforms) and the single normalization pass each value goes through.

The model's ``clean()`` and the profile forms both call these helpers, so a
value stored by onboarding and the same value stored by the profile editor
cannot drift apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.utils.translation import gettext_lazy as _

# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------

# A curated list, not the ISO register: agents pick from what clients in our
# markets actually ask for, and a closed set keeps the value queryable.
LANGUAGE_CHOICES: tuple[tuple[str, str], ...] = (
    ("en", "English"),
    ("es", "Spanish"),
    ("zh", "Chinese"),
    ("tl", "Tagalog"),
    ("vi", "Vietnamese"),
    ("ar", "Arabic"),
    ("fr", "French"),
    ("ko", "Korean"),
    ("ru", "Russian"),
    ("de", "German"),
    ("hi", "Hindi"),
    ("ur", "Urdu"),
    ("pt", "Portuguese"),
    ("fa", "Persian"),
    ("am", "Amharic"),
    ("it", "Italian"),
    ("pl", "Polish"),
    ("ja", "Japanese"),
    ("he", "Hebrew"),
    ("bn", "Bengali"),
    ("uk", "Ukrainian"),
    ("so", "Somali"),
    ("ht", "Haitian Creole"),
    ("sw", "Swahili"),
    ("tr", "Turkish"),
    ("th", "Thai"),
    ("ne", "Nepali"),
    ("pa", "Punjabi"),
    ("gu", "Gujarati"),
    ("ta", "Tamil"),
    ("te", "Telugu"),
    ("asl", "American Sign Language"),
)

LANGUAGE_NAMES: dict[str, str] = dict(LANGUAGE_CHOICES)
_LANGUAGE_ORDER: dict[str, int] = {
    code: index for index, (code, _name) in enumerate(LANGUAGE_CHOICES)
}

MAX_LANGUAGES = 10

# ---------------------------------------------------------------------------
# Specialties
# ---------------------------------------------------------------------------

# Closed brokerage practice areas — kept queryable for the agent directory.
SPECIALTY_CHOICES: tuple[tuple[str, str], ...] = (
    ("residential", "Residential"),
    ("commercial", "Commercial"),
    ("luxury", "Luxury"),
    ("relocation", "Relocation"),
    ("new_construction", "New construction"),
    ("property_management", "Property management"),
    ("land", "Land"),
    ("investment", "Investment"),
    ("short_sales", "Short sales / REO"),
    ("first_time_buyers", "First-time buyers"),
    ("senior_living", "Senior living"),
    ("rentals", "Rentals"),
)

SPECIALTY_NAMES: dict[str, str] = dict(SPECIALTY_CHOICES)
_SPECIALTY_ORDER: dict[str, int] = {
    code: index for index, (code, _name) in enumerate(SPECIALTY_CHOICES)
}

MAX_SPECIALTIES = 8

# ---------------------------------------------------------------------------
# Preferred contact method
# ---------------------------------------------------------------------------

PREFERRED_CONTACT_CHOICES: tuple[tuple[str, str], ...] = (
    ("email", "Email"),
    ("phone", "Phone call"),
    ("text", "Text message"),
)

PREFERRED_CONTACT_VALUES = {value for value, _label in PREFERRED_CONTACT_CHOICES}

# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------

MAX_URL_LENGTH = 255
BIO_MAX_LENGTH = 1500
MAX_LICENSE_FUTURE_YEARS = 10


@dataclass(frozen=True)
class SocialPlatform:
    """One supported social destination.

    ``hosts`` is an allowlist rather than decoration: a LinkedIn field that
    silently accepts any URL is a link-injection surface on every page that
    later renders an agent's profile.
    """

    field: str
    prop: str
    label: str
    hosts: tuple[str, ...]
    placeholder: str


SOCIAL_PLATFORMS: tuple[SocialPlatform, ...] = (
    SocialPlatform(
        field="linkedin_url",
        prop="linkedinUrl",
        label="LinkedIn",
        hosts=("linkedin.com",),
        placeholder="https://www.linkedin.com/in/your-profile",
    ),
    SocialPlatform(
        field="facebook_url",
        prop="facebookUrl",
        label="Facebook",
        hosts=("facebook.com", "fb.com"),
        placeholder="https://www.facebook.com/your-page",
    ),
    SocialPlatform(
        field="instagram_url",
        prop="instagramUrl",
        label="Instagram",
        hosts=("instagram.com",),
        placeholder="https://www.instagram.com/your-handle",
    ),
    SocialPlatform(
        field="x_url",
        prop="xUrl",
        label="X",
        hosts=("x.com", "twitter.com"),
        placeholder="https://x.com/your-handle",
    ),
)

SOCIAL_PLATFORM_BY_FIELD: dict[str, SocialPlatform] = {
    platform.field: platform for platform in SOCIAL_PLATFORMS
}

_MULTISPACE_RE = re.compile(r"\s+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


# ---------------------------------------------------------------------------
# Normalizers
# ---------------------------------------------------------------------------


def normalize_name(value: str) -> str:
    """Collapse whitespace in a person-name-shaped value. Blank stays blank."""
    return _MULTISPACE_RE.sub(" ", (value or "").strip())


def normalize_license_number(value: str) -> str:
    """License numbers are printed uppercase; store them that way."""
    return _MULTISPACE_RE.sub(" ", (value or "").strip()).upper()


def normalize_bio(value: str) -> str:
    """Trim, normalize line endings, and cap runs of blank lines."""
    raw = (value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return ""
    raw = _BLANK_LINES_RE.sub("\n\n", raw)
    if len(raw) > BIO_MAX_LENGTH:
        raise ValidationError(
            _("Keep your bio under %(max)d characters. Yours is %(count)d.")
            % {"max": BIO_MAX_LENGTH, "count": len(raw)},
            code="max_length",
        )
    return raw


def normalize_url(
    value: str,
    *,
    allowed_hosts: tuple[str, ...] = (),
    label: str = "",
) -> str:
    """Return a canonical ``https://host/path`` URL, or raise ValidationError.

    A bare ``example.com`` is accepted and upgraded to ``https://`` — asking an
    agent to type a scheme is the kind of friction that leaves the field empty.
    Credentials in the URL and non-web schemes are rejected outright.
    """
    raw = (value or "").strip()
    if not raw:
        return ""
    if "//" not in raw:
        raw = f"https://{raw}"

    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValidationError(
            _("Enter a web address that starts with https://."), code="invalid"
        )
    if parsed.username or parsed.password:
        raise ValidationError(
            _("Remove the username and password from the web address."), code="invalid"
        )

    host = (parsed.hostname or "").lower()
    if not host or "." not in host:
        raise ValidationError(
            _("Enter a complete web address, for example https://example.com."),
            code="invalid",
        )
    if allowed_hosts and not any(
        host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts
    ):
        raise ValidationError(
            _("Enter a %(label)s address on %(hosts)s.")
            % {"label": label or "link", "hosts": " or ".join(allowed_hosts)},
            code="invalid",
        )

    netloc = f"{host}:{parsed.port}" if parsed.port else host
    normalized = urlunsplit(
        (parsed.scheme.lower(), netloc, parsed.path, parsed.query, parsed.fragment)
    )
    if len(normalized) > MAX_URL_LENGTH:
        raise ValidationError(
            _("Web addresses must be %(max)d characters or fewer.")
            % {"max": MAX_URL_LENGTH},
            code="max_length",
        )
    URLValidator(schemes=["http", "https"])(normalized)
    return normalized


def normalize_languages(values) -> list[str]:
    """Return deduplicated, ordered language codes from the supported set."""
    if values in (None, ""):
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set, frozenset)):
        raise ValidationError(_("Choose languages from the list."), code="invalid")

    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in values:
        code = str(raw).strip().lower()
        if not code:
            continue
        if code not in LANGUAGE_NAMES:
            raise ValidationError(
                _("“%(code)s” is not one of the languages we support.")
                % {"code": code[:32]},
                code="invalid",
            )
        if code in seen:
            continue
        seen.add(code)
        cleaned.append(code)

    if len(cleaned) > MAX_LANGUAGES:
        raise ValidationError(
            _("Choose up to %(max)d languages.") % {"max": MAX_LANGUAGES},
            code="max_length",
        )
    cleaned.sort(key=_LANGUAGE_ORDER.__getitem__)
    return cleaned


def normalize_preferred_contact_method(value: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    if raw not in PREFERRED_CONTACT_VALUES:
        raise ValidationError(_("Choose how you prefer to be contacted."), "invalid")
    return raw


def normalize_specialties(values) -> list[str]:
    """Return deduplicated, ordered specialty codes from the supported set."""
    if values in (None, ""):
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set, frozenset)):
        raise ValidationError(_("Choose specialties from the list."), code="invalid")

    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in values:
        code = str(raw).strip().lower()
        if not code:
            continue
        if code not in SPECIALTY_NAMES:
            raise ValidationError(
                _("“%(code)s” is not one of the specialties we support.")
                % {"code": code[:32]},
                code="invalid",
            )
        if code in seen:
            continue
        seen.add(code)
        cleaned.append(code)

    if len(cleaned) > MAX_SPECIALTIES:
        raise ValidationError(
            _("Choose up to %(max)d specialties.") % {"max": MAX_SPECIALTIES},
            code="max_length",
        )
    cleaned.sort(key=_SPECIALTY_ORDER.__getitem__)
    return cleaned


def language_options() -> list[dict[str, str]]:
    return [{"code": code, "name": name} for code, name in LANGUAGE_CHOICES]


def specialty_options() -> list[dict[str, str]]:
    return [{"code": code, "name": name} for code, name in SPECIALTY_CHOICES]


def contact_method_options() -> list[dict[str, str]]:
    return [
        {"value": value, "label": label} for value, label in PREFERRED_CONTACT_CHOICES
    ]


def social_platform_options() -> list[dict[str, str]]:
    return [
        {
            "name": platform.field,
            "prop": platform.prop,
            "label": platform.label,
            "placeholder": platform.placeholder,
        }
        for platform in SOCIAL_PLATFORMS
    ]
