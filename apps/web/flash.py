"""One-shot flash messages for Inertia page responses.

Set on a successful mutating request, then popped into shared Inertia props on
the following render so the client can toast without relying on visit
callbacks that may not run across a redirect.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

SESSION_KEY = "inertia_flash"


def set_flash(request: HttpRequest, *, level: str, message: str) -> None:
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
