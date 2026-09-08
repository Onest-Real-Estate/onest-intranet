"""Inertia flash helpers."""

from __future__ import annotations

import pytest

from apps.web.flash import pop_flash, set_flash


@pytest.mark.django_db
def test_set_and_pop_flash(client, django_user_model):
    from django.test import RequestFactory

    request = RequestFactory().get("/")
    # Session middleware is not applied on RequestFactory by default.
    from django.contrib.sessions.backends.db import SessionStore

    request.session = SessionStore()
    request.session.create()

    assert pop_flash(request) is None
    set_flash(request, level="success", message="Draft saved")
    assert pop_flash(request) == {"level": "success", "message": "Draft saved"}
    assert pop_flash(request) is None
