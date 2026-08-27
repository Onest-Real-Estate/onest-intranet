"""DocuSeal client for agent-contract templates and signing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

import jwt
from django.conf import settings
from docuseal._api import DocusealApi
from docuseal._http import ApiError

logger = logging.getLogger(__name__)

PREFILL_ROLE = "Prefill"
SIGNER_ROLE = "Agent"
SIGNING_FIELD_TYPES = frozenset({"signature", "initials", "date", "datenow", "stamp"})
_OPEN_TIMEOUT = 10
_READ_TIMEOUT = 30


class DocuSealError(Exception):
    """Raised when DocuSeal is misconfigured or returns an error."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class DocuSealNotConfigured(DocuSealError):
    """API key or base URL missing — signing must stay disabled."""


@dataclass(frozen=True)
class DocuSealSubmitter:
    id: int | None
    email: str
    slug: str
    embed_src: str
    external_id: str
    role: str = ""


@dataclass(frozen=True)
class DocuSealSubmission:
    id: int
    submitters: tuple[DocuSealSubmitter, ...]

    @property
    def primary_submitter(self) -> DocuSealSubmitter:
        if not self.submitters:
            raise DocuSealError("DocuSeal submission returned no submitters.")
        return self.submitters[0]

    def submitter_by_role(self, role: str) -> DocuSealSubmitter | None:
        wanted = (role or "").strip().lower()
        for submitter in self.submitters:
            if submitter.role.strip().lower() == wanted:
                return submitter
        return None

    def agent_submitter(self) -> DocuSealSubmitter:
        found = self.submitter_by_role(SIGNER_ROLE)
        if found is not None:
            return found
        # Single-submitter templates still work for Agent-only flows.
        if len(self.submitters) == 1:
            return self.submitters[0]
        raise DocuSealError("DocuSeal submission missing Agent submitter.")


@dataclass(frozen=True)
class DocuSealTemplateField:
    name: str
    field_type: str
    role: str
    required: bool


@dataclass(frozen=True)
class DocuSealTemplate:
    id: int
    name: str
    external_id: str
    fields: tuple[DocuSealTemplateField, ...]

    @property
    def merge_field_names(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    field.name
                    for field in self.fields
                    if field.name
                    and field.field_type not in SIGNING_FIELD_TYPES
                    and field.role.strip().lower() != SIGNER_ROLE.lower()
                }
            )
        )

    @property
    def has_agent_signature(self) -> bool:
        return any(
            field.field_type == "signature"
            and field.role.strip().lower() == SIGNER_ROLE.lower()
            for field in self.fields
        )


def is_docuseal_configured() -> bool:
    api_origin = (getattr(settings, "DOCUSEAL_API_URL", "") or "").strip()
    public_origin = (settings.DOCUSEAL_BASE_URL or "").strip()
    return bool(settings.DOCUSEAL_API_KEY and (api_origin or public_origin))


def is_docuseal_builder_configured() -> bool:
    return is_docuseal_configured() and bool(
        (getattr(settings, "DOCUSEAL_USER_EMAIL", "") or "").strip()
    )


def _api_base_url() -> str:
    """Server-reachable DocuSeal API base (…/api).

    Prefer ``DOCUSEAL_API_URL`` so docker web/celery can call ``http://docuseal:3000``
    while browsers keep using ``DOCUSEAL_BASE_URL`` (``http://localhost:3000``).
    """
    base = (getattr(settings, "DOCUSEAL_API_URL", "") or "").strip().rstrip("/")
    if not base:
        base = settings.DOCUSEAL_BASE_URL.rstrip("/")
    if base.endswith("/api"):
        return base
    return f"{base}/api"


def _client() -> DocusealApi:
    if not is_docuseal_configured():
        raise DocuSealNotConfigured("DocuSeal API is not configured.")
    return DocusealApi(
        key=settings.DOCUSEAL_API_KEY,
        url=_api_base_url(),
        open_timeout=_OPEN_TIMEOUT,
        read_timeout=_READ_TIMEOUT,
    )


def embed_host() -> str:
    """Hostname (no scheme) for ``DocusealBuilder`` / ``DocusealForm`` ``host``."""
    base = _embed_base_url()
    return base.removeprefix("https://").removeprefix("http://").rstrip("/")


def embed_protocol() -> str:
    """``http`` or ``https`` from ``DOCUSEAL_BASE_URL`` (local Docker is HTTP)."""
    base = _embed_base_url().lower()
    if base.startswith("http://"):
        return "http"
    return "https"


def embed_origin() -> str:
    """Browser-reachable DocuSeal origin including scheme (no trailing slash)."""
    return f"{embed_protocol()}://{embed_host()}"


def _api_origin() -> str:
    """Server-reachable DocuSeal origin (scheme + host, no ``/api``)."""
    base = _api_base_url()
    if base.endswith("/api"):
        base = base[: -len("/api")]
    return base.rstrip("/")


_embeds_probe_at: float | None = None
_embeds_probe_ok: bool = False


def docuseal_embeds_available() -> bool:
    """Whether DocuSeal serves real embed JS (Pro), not the OSS DummyBuilder stub.

    Community ``docuseal/docuseal`` returns a tiny ``builder.js`` / ``form.js`` that
    only renders “Upgrade to Pro”. Embedded builder/signing need the Pro image.
    """
    global _embeds_probe_at, _embeds_probe_ok
    if not is_docuseal_configured():
        return False
    now = time.monotonic()
    if _embeds_probe_at is not None and now - _embeds_probe_at < 60:
        return _embeds_probe_ok
    ok = _probe_docuseal_embeds()
    _embeds_probe_at = now
    _embeds_probe_ok = ok
    return ok


def _probe_docuseal_embeds() -> bool:
    url = f"{_api_origin()}/js/builder.js"
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=3) as response:
            body = response.read(4096).decode("utf-8", errors="ignore")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.info("DocuSeal embed probe failed for %s: %s", url, exc)
        return False
    if "DummyBuilder" in body or "Upgrade to Pro" in body:
        return False
    return len(body) > 2048


def _embed_base_url() -> str:
    """Public DocuSeal origin for ``/s/<slug>`` embed links (browser-reachable)."""
    base = settings.DOCUSEAL_BASE_URL.rstrip("/")
    if base.endswith("/api"):
        return base[: -len("/api")] or base
    return base


def authorize_docuseal_webhook(
    *,
    raw_body: bytes,
    signature_header: str = "",
    url_token: str = "",
) -> bool:
    """Authorize an inbound DocuSeal webhook.

    Self-hosted DocuSeal (compose) only offers a Webhook URL field — no HMAC
    secret UI. For that setup, put a shared token in the URL you paste into
    DocuSeal, e.g. ``/webhooks/docuseal/contracts?token=<DOCUSEAL_WEBHOOK_SECRET>``.

    Cloud / newer DocuSeal builds may send ``X-Docuseal-Signature``; when that
    header is present we verify HMAC-SHA256 instead.

    Empty ``DOCUSEAL_WEBHOOK_SECRET`` always fails closed.
    """
    secret = (settings.DOCUSEAL_WEBHOOK_SECRET or "").strip()
    if not secret:
        return False

    header = (signature_header or "").strip()
    if header:
        if "." in header:
            timestamp_s, provided = header.split(".", 1)
            try:
                ts = int(timestamp_s)
            except ValueError:
                return False
            if abs(time.time() - ts) > 300:
                return False
            signed = f"{timestamp_s}.".encode() + raw_body
            expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, provided)
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, header)

    token = (url_token or "").strip()
    if not token:
        return False
    return hmac.compare_digest(secret, token)


def verify_webhook_signature(*, raw_body: bytes, signature_header: str) -> bool:
    """Backward-compatible alias for HMAC-only verification."""
    return authorize_docuseal_webhook(
        raw_body=raw_body,
        signature_header=signature_header,
        url_token="",
    )


def _api_error_status(exc: ApiError) -> int | None:
    message = str(exc)
    if message.startswith("API Error "):
        try:
            return int(message.split(":", 1)[0].removeprefix("API Error "))
        except ValueError:
            return None
    return None


def _raise_api(exc: ApiError, *, log_message: str) -> None:
    status_code = _api_error_status(exc)
    detail = str(exc)
    # SDK format: "API Error 404: {...}"
    if ":" in detail:
        body = detail.split(":", 1)[1].strip()
        if "Pro Edition" in body:
            detail = (
                "Creating templates from PDF via API requires DocuSeal Pro. "
                "Use the embedded builder upload instead."
            )
        elif body.startswith("{") or body.startswith("["):
            detail = "DocuSeal rejected the request."
        else:
            detail = body or "DocuSeal rejected the request."
    else:
        detail = "DocuSeal rejected the request."
    logger.warning("%s status=%s", log_message, status_code)
    raise DocuSealError(detail, status_code=status_code) from exc


def _parse_submitter(raw: dict[str, Any]) -> DocuSealSubmitter:
    embed = (raw.get("embed_src") or "").strip()
    slug = (raw.get("slug") or "").strip()
    if not embed and slug:
        embed = f"{_embed_base_url()}/s/{slug}"
    return DocuSealSubmitter(
        id=raw.get("id") if isinstance(raw.get("id"), int) else None,
        email=str(raw.get("email") or ""),
        slug=slug,
        embed_src=embed,
        external_id=str(raw.get("external_id") or ""),
        role=str(raw.get("role") or ""),
    )


def _as_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    # Some SDK responses may be attribute bags.
    data = getattr(value, "__dict__", None)
    if isinstance(data, dict) and data:
        return data
    return None


def _parse_submission(payload: Any) -> DocuSealSubmission:
    """Normalize create-submission responses (object or submitter list)."""
    if isinstance(payload, list):
        submitters: list[DocuSealSubmitter] = []
        submission_id = None
        for item in payload:
            mapped = _as_mapping(item)
            if mapped is None:
                continue
            submitters.append(_parse_submitter(mapped))
            if mapped.get("submission_id") is not None:
                submission_id = int(mapped["submission_id"])
        if submission_id is None and submitters and submitters[0].id is not None:
            raise DocuSealError("DocuSeal response missing submission_id.")
        if submission_id is None:
            raise DocuSealError("DocuSeal response missing submission id.")
        return DocuSealSubmission(id=submission_id, submitters=tuple(submitters))

    mapped = _as_mapping(payload)
    if mapped is None:
        raise DocuSealError("Unexpected DocuSeal submission response shape.")

    submission_id = mapped.get("id")
    if submission_id is None:
        raise DocuSealError("DocuSeal response missing submission id.")
    raw_submitters = mapped.get("submitters") or []
    if not isinstance(raw_submitters, list):
        raise DocuSealError("DocuSeal response missing submitters.")
    submitters = []
    for item in raw_submitters:
        entry = _as_mapping(item)
        if entry is not None:
            submitters.append(_parse_submitter(entry))
    return DocuSealSubmission(id=int(submission_id), submitters=tuple(submitters))


def _role_for_submitter_uuid(
    submitters: list[dict[str, Any]],
    submitter_uuid: str,
) -> str:
    for item in submitters:
        if str(item.get("uuid") or "") == submitter_uuid:
            return str(item.get("name") or "").strip()
    return ""


def _parse_template(payload: Any) -> DocuSealTemplate:
    mapped = _as_mapping(payload)
    if mapped is None:
        raise DocuSealError("Unexpected DocuSeal template response shape.")
    template_id = mapped.get("id")
    if template_id is None:
        raise DocuSealError("DocuSeal template response missing id.")

    raw_submitters = mapped.get("submitters") or []
    submitter_rows: list[dict[str, Any]] = []
    if isinstance(raw_submitters, list):
        for item in raw_submitters:
            entry = _as_mapping(item)
            if entry is not None:
                submitter_rows.append(entry)

    fields: list[DocuSealTemplateField] = []
    raw_fields = mapped.get("fields") or []
    if isinstance(raw_fields, list):
        for item in raw_fields:
            entry = _as_mapping(item)
            if entry is None:
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            submitter_uuid = str(entry.get("submitter_uuid") or "")
            fields.append(
                DocuSealTemplateField(
                    name=name,
                    field_type=str(entry.get("type") or "text").strip().lower(),
                    role=_role_for_submitter_uuid(submitter_rows, submitter_uuid),
                    required=bool(entry.get("required")),
                )
            )

    return DocuSealTemplate(
        id=int(template_id),
        name=str(mapped.get("name") or ""),
        external_id=str(mapped.get("external_id") or ""),
        fields=tuple(fields),
    )


def build_builder_token(
    *,
    template_id: int | None = None,
    external_id: str = "",
    name: str = "",
    document_urls: list[str] | None = None,
) -> str:
    """HS256 JWT for ``<DocusealBuilder>`` (signed with the API key)."""
    if not is_docuseal_builder_configured():
        raise DocuSealNotConfigured("DocuSeal builder is not configured.")

    payload: dict[str, Any] = {
        "user_email": settings.DOCUSEAL_USER_EMAIL.strip(),
    }
    if template_id is not None:
        payload["template_id"] = int(template_id)
    if external_id:
        payload["external_id"] = external_id
    if name:
        payload["name"] = name
    if document_urls:
        payload["document_urls"] = list(document_urls)
        # Hub uploads plain PDFs; avoid auto-extracting AcroForm junk.
        payload["extract_fields"] = False

    return jwt.encode(payload, settings.DOCUSEAL_API_KEY, algorithm="HS256")


def create_template_from_pdf(
    *,
    name: str,
    pdf_bytes: bytes,
    external_id: str,
    folder_name: str = "Agent contracts",
) -> DocuSealTemplate:
    """Create or update a DocuSeal template from PDF bytes (via external_id)."""
    body: dict[str, Any] = {
        "name": name,
        "external_id": external_id,
        "folder_name": folder_name,
        "shared_link": False,
        "flatten": True,
        "documents": [
            {
                "name": name,
                "file": base64.b64encode(pdf_bytes).decode("ascii"),
            }
        ],
    }
    client = _client()
    try:
        payload = client.create_template_from_pdf(body)
    except ApiError as exc:
        _raise_api(exc, log_message="docuseal create_template_from_pdf failed")
    except OSError as exc:
        logger.warning(
            "docuseal create_template_from_pdf transport error: %s",
            exc,
        )
        raise DocuSealError("Could not reach DocuSeal.") from exc
    return _parse_template(payload)


def get_template(template_id: int) -> DocuSealTemplate:
    client = _client()
    try:
        payload = client.get_template(template_id)
    except ApiError as exc:
        _raise_api(exc, log_message="docuseal get_template failed")
    except OSError as exc:
        logger.warning("docuseal get_template transport error")
        raise DocuSealError("Could not reach DocuSeal.") from exc
    return _parse_template(payload)


def create_submission(
    *,
    template_id: int,
    submitters: list[dict[str, Any]],
    name: str = "",
    expire_at_iso: str | None = None,
    order: str = "preserved",
) -> DocuSealSubmission:
    """Create a submission against a DocuSeal template (Prefill + Agent)."""
    body: dict[str, Any] = {
        "template_id": int(template_id),
        "send_email": False,
        "send_sms": False,
        "order": order,
        "submitters": submitters,
    }
    if name:
        body["name"] = name
    if expire_at_iso:
        body["expire_at"] = expire_at_iso

    client = _client()
    try:
        payload = client.create_submission(body)
    except ApiError as exc:
        _raise_api(exc, log_message="docuseal create_submission failed")
    except OSError as exc:
        logger.warning("docuseal create_submission transport error")
        raise DocuSealError("Could not reach DocuSeal.") from exc
    return _parse_submission(payload)


def get_submission(submission_id: int) -> DocuSealSubmission:
    client = _client()
    try:
        payload = client.get_submission(submission_id)
    except ApiError as exc:
        _raise_api(exc, log_message="docuseal get_submission failed")
    except OSError as exc:
        logger.warning("docuseal get_submission transport error")
        raise DocuSealError("Could not reach DocuSeal.") from exc
    return _parse_submission(payload)


def _document_urls(payload: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(payload, list):
        for item in payload:
            mapped = _as_mapping(item)
            if mapped and mapped.get("url"):
                urls.append(str(mapped["url"]))
        return urls

    mapped = _as_mapping(payload)
    if mapped is None:
        return urls
    docs = mapped.get("documents") or mapped.get("files") or []
    if isinstance(docs, list):
        for item in docs:
            doc = _as_mapping(item)
            if doc and doc.get("url"):
                urls.append(str(doc["url"]))
    if mapped.get("url"):
        urls.append(str(mapped["url"]))
    return urls


def _download_bytes(url: str, *, auth_token: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "X-Auth-Token": auth_token,
            "User-Agent": "oNEST-DocuSeal-Client",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=_READ_TIMEOUT) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise DocuSealError(
            "Signed PDF download failed.",
            status_code=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        raise DocuSealError("Could not download signed PDF bytes.") from exc


def download_submission_documents(submission_id: int) -> bytes:
    """Download the combined PDF for a submission (partial or completed)."""
    client = _client()
    try:
        payload = client.get_submission_documents(submission_id, params={"merge": True})
    except ApiError as exc:
        logger.warning(
            "docuseal download documents failed submission_id=%s", submission_id
        )
        raise DocuSealError(
            "DocuSeal could not return signed documents.",
        ) from exc
    except OSError as exc:
        logger.warning("docuseal download documents transport error")
        raise DocuSealError("Could not download signed documents.") from exc

    urls = _document_urls(payload)
    if not urls:
        raise DocuSealError("DocuSeal documents response had no download URL.")

    data = _download_bytes(urls[0], auth_token=settings.DOCUSEAL_API_KEY)
    if not data:
        raise DocuSealError("Signed PDF download failed.")
    return data


def prefill_submitter_payload(
    *,
    email: str,
    values: dict[str, str],
    name: str = "oNEST Prefill",
) -> dict[str, Any]:
    """Build the Prefill submitter that auto-completes with readonly values."""
    fields = [
        {
            "name": key,
            "default_value": value,
            "readonly": True,
        }
        for key, value in values.items()
        if key
    ]
    return {
        "role": PREFILL_ROLE,
        "email": email,
        "name": name,
        "completed": True,
        "send_email": False,
        "values": values,
        "fields": fields,
    }


def agent_submitter_payload(
    *,
    email: str,
    name: str,
    external_id: str,
) -> dict[str, Any]:
    return {
        "role": SIGNER_ROLE,
        "email": email,
        "name": name,
        "external_id": external_id,
        "send_email": False,
    }
