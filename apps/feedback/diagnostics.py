"""What the browser is allowed to tell us, and what is scrubbed before storage.

This module is the security core of the feedback module. A support form that
quietly hoovers up context is the easiest way in the whole product to end up
storing somebody's session token in a table that support staff can read.

Three rules, in order:

1. **Minimise.** The client sends a fixed, small set of fields. Anything else
   it offers is dropped — there is no passthrough dictionary, so a future
   frontend cannot widen the capture by adding a key.
2. **Redact.** The page URL is the one field that routinely carries secrets:
   password-reset tokens, invite codes, signed download links, SSO state. Every
   query parameter is dropped unless it is on a tiny allowlist, and the
   fragment goes entirely.
3. **Disclose.** :func:`disclosure_lines` is the exact text the form shows the
   submitter, generated from the same constants that do the capturing, so the
   promise and the behaviour cannot drift apart.

None of this trusts the client. The URL is re-validated as same-origin here,
server-side, because a submitted "current page" pointing at another host is
either a bug or an attempt to make a support ticket look like it came from
somewhere it did not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

#: Query parameters worth keeping. Everything else is dropped — an allowlist
#: rather than a denylist, because the next secret-bearing parameter name is
#: one nobody has thought of yet.
ALLOWED_QUERY_KEYS: frozenset[str] = frozenset(
    {"page", "status", "category", "priority", "view", "tab", "sort", "q"}
)

#: Even an allowlisted parameter is dropped when its *value* looks like a
#: credential. `q` is a search term, but somebody pasting a token into a search
#: box should not have it stored here.
_SECRET_VALUE = re.compile(
    r"""(
        ^(?:ey[A-Za-z0-9_-]{10,})            # JWT
        | ^[A-Za-z0-9_-]{32,}$               # long opaque token
        | ^(?:sk|pk|ghp|gho|xox[baprs])[-_]  # common key prefixes
    )""",
    re.VERBOSE,
)

#: Redaction marker. Stored rather than silently dropping the key, so a triager
#: can see that a parameter existed without learning its value.
REDACTED = "[redacted]"

#: The complete set of browser facts the client may report. A key not listed
#: here never reaches the database, whatever the form posts.
ALLOWED_METADATA_KEYS: frozenset[str] = frozenset(
    {"viewport", "locale", "timezone", "platform", "browser"}
)

#: Per-value length cap. Metadata is labels, not payloads.
MAX_METADATA_VALUE = 80

_VIEWPORT = re.compile(r"^\d{2,5}x\d{2,5}$")
_LOCALE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
_TIMEZONE = re.compile(r"^[A-Za-z][A-Za-z0-9_+\-]*(?:/[A-Za-z0-9_+\-]+){0,2}$")
_SIMPLE = re.compile(r"^[A-Za-z0-9 ._()\-]{1,80}$")

_METADATA_SHAPES: dict[str, re.Pattern[str]] = {
    "viewport": _VIEWPORT,
    "locale": _LOCALE,
    "timezone": _TIMEZONE,
    "platform": _SIMPLE,
    "browser": _SIMPLE,
}


@dataclass(frozen=True)
class Diagnostics:
    """The scrubbed context stored beside a ticket."""

    page_url: str
    metadata: dict[str, str]

    def as_dict(self) -> dict[str, object]:
        return {"pageUrl": self.page_url, "metadata": dict(self.metadata)}


def _is_secretish(value: str) -> bool:
    return bool(_SECRET_VALUE.search(value.strip()))


def redact_url(raw: str, *, allowed_hosts: set[str]) -> str:
    """Return a storable version of the page the submitter was on.

    Same-origin is enforced here rather than trusted from the client: a URL on
    another host is refused outright, because a ticket that claims to come from
    a page we do not serve is either a bug or someone shaping the record.

    A relative URL is accepted and kept relative — that is what the frontend
    sends in the ordinary case, and it carries no host to disagree about.
    """
    value = (raw or "").strip()
    if not value:
        return ""
    if len(value) > 2000:
        raise ValidationError({"pageUrl": _("That address is too long to record.")})

    parts = urlsplit(value)

    if parts.scheme and parts.scheme not in {"http", "https"}:
        raise ValidationError({"pageUrl": _("Only web addresses can be recorded.")})
    if parts.netloc:
        host = parts.netloc.split("@")[-1].split(":")[0].lower()
        if host not in allowed_hosts:
            raise ValidationError(
                {
                    "pageUrl": _(
                        "That address is not part of this site, so it was not recorded."
                    )
                }
            )

    kept: list[str] = []
    for pair in parts.query.split("&"):
        if not pair:
            continue
        key, _sep, raw_value = pair.partition("=")
        if key not in ALLOWED_QUERY_KEYS:
            continue
        kept.append(f"{key}={REDACTED}" if _is_secretish(raw_value) else pair)

    # The fragment never survives. It is invisible to the server in normal
    # operation, is a favourite place to park tokens, and tells a triager
    # nothing they need.
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(kept), ""))


def clean_metadata(raw: object) -> dict[str, str]:
    """Keep only allowlisted keys whose values match their declared shape.

    A value that fails its pattern is dropped rather than truncated: the point
    of the shape check is that "1280x720" is a viewport and anything else is
    something the client should not have been sending.
    """
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, str] = {}
    for key in sorted(ALLOWED_METADATA_KEYS):
        value = raw.get(key)
        if not isinstance(value, str):
            continue
        value = value.strip()[:MAX_METADATA_VALUE]
        if not value or _is_secretish(value):
            continue
        shape = _METADATA_SHAPES.get(key)
        if shape is not None and not shape.match(value):
            continue
        cleaned[key] = value
    return cleaned


def build_diagnostics(
    *, page_url: str, metadata: object, allowed_hosts: set[str]
) -> Diagnostics:
    return Diagnostics(
        page_url=redact_url(page_url, allowed_hosts=allowed_hosts),
        metadata=clean_metadata(metadata),
    )


def disclosure_lines() -> list[str]:
    """Exactly what the form promises, generated from what the code does.

    Written here rather than in a template so the disclosure cannot drift away
    from the capture. If someone widens `ALLOWED_METADATA_KEYS`, this sentence
    changes with it and the copy review happens automatically.
    """
    fields = ", ".join(sorted(ALLOWED_METADATA_KEYS))
    return [
        "Your name, work email, and office, so support can reply.",
        (
            "The page you were on when you opened this form, with any "
            "query values that could be secrets removed and the "
            "part after # dropped entirely."
        ),
        f"Basic browser facts: {fields}. Nothing else is read from your device.",
        "Anything you type, and any screenshot you choose to attach.",
    ]
