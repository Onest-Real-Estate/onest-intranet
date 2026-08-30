"""One-shot flash messages for Inertia page responses.

Set on a successful mutating request, then popped into shared Inertia props on
the following render so the client can toast without relying on visit
callbacks that may not run across a redirect.

Levels match Django ``django.contrib.messages`` tags so product code can use
the same vocabulary as ``messages.success`` / ``messages.warning`` / etc.
"""

from __future__ import annotations

from typing import Any, Literal

from django.http import HttpRequest

SESSION_KEY = "inertia_flash"

FlashLevel = Literal["debug", "info", "success", "warning", "error"]

FLASH_LEVELS: frozenset[str] = frozenset(
    {"debug", "info", "success", "warning", "error"}
)


def set_flash(request: HttpRequest, *, level: FlashLevel | str, message: str) -> None:
    request.session[SESSION_KEY] = {"level": level, "message": message}


def pop_flash(request: HttpRequest) -> dict[str, Any] | None:
    flash = request.session.pop(SESSION_KEY, None)
    if not isinstance(flash, dict):
        return None
    level = flash.get("level")
    message = flash.get("message")
    if not isinstance(level, str) or not isinstance(message, str) or not message:
        return None
    return {"level": level, "message": message}
