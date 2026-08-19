from __future__ import annotations

import uuid

from .context import AuditContext, reset_audit_context, set_audit_context


def _sanitize_header(value: str, *, limit: int) -> str:
    value = (value or "").replace("\r", " ").replace("\n", " ").strip()
    return value[:limit]


class AuditContextMiddleware:
    """Attach per-request audit context using contextvars."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raw_request_id = request.headers.get("X-Request-ID", "")
        request_id = _sanitize_header(raw_request_id, limit=255) or str(uuid.uuid4())
        remote_addr = _sanitize_header(request.META.get("REMOTE_ADDR", ""), limit=128)
        user_agent = _sanitize_header(
            request.META.get("HTTP_USER_AGENT", ""), limit=512
        )
        request.audit_request_id = request_id
        ctx = AuditContext(
            request_id=request_id,
            source="request",
            channel=request.method,
            remote_addr=remote_addr,
            user_agent=user_agent,
        )
        token = set_audit_context(ctx)
        try:
            return self.get_response(request)
        finally:
            reset_audit_context(token)
