"""Short-lived, self-only Centrifugo credentials for the dashboard journey."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import cast

import jwt
from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.user.models import User
from apps.user.services.onboarding_state import journey_applies_to
from apps.user.services.onboarding_stream import (
    configured,
    opaque_user_key,
    private_channel,
)
from apps.web.authorization import enforce_policy

TOKEN_SECONDS = 60
TOKEN_REQUESTS_PER_MINUTE = 24


@enforce_policy("onboarding_stream_token")
@require_GET
def onboarding_stream_token(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return JsonResponse({"error": "unavailable"}, status=403)
    user = cast(User, request.user)
    if not user.is_active or user.pk is None or not journey_applies_to(user):
        return JsonResponse({"error": "unavailable"}, status=403)
    if not configured():
        return JsonResponse({"error": "unavailable"}, status=503)

    # Django's authenticated session is the only credential source. The cache
    # key contains a digest, never a session cookie or a sequential user ID.
    session_key = request.session.session_key
    if not session_key:
        return JsonResponse({"error": "unavailable"}, status=403)
    key = "onboarding-live-token:" + hashlib.sha256(session_key.encode()).hexdigest()
    count = 1 if cache.add(key, 1, timeout=60) else cache.incr(key)
    if count > TOKEN_REQUESTS_PER_MINUTE:
        response = JsonResponse({"error": "rate_limited"}, status=429)
        response["Retry-After"] = "60"
        return response

    expires = int((timezone.now() + timedelta(seconds=TOKEN_SECONDS)).timestamp())
    user_id = int(user.pk)
    subject = opaque_user_key(user_id)
    secret = settings.CENTRIFUGO_HMAC_SECRET
    channel = private_channel(user_id)
    response = JsonResponse(
        {
            "url": settings.CENTRIFUGO_WS_URL,
            "channel": channel,
            "connectionToken": jwt.encode(
                {"sub": subject, "exp": expires}, secret, algorithm="HS256"
            ),
            "subscriptionToken": jwt.encode(
                {"sub": subject, "channel": channel, "exp": expires},
                secret,
                algorithm="HS256",
            ),
        }
    )
    response["Cache-Control"] = "no-store"
    return response
