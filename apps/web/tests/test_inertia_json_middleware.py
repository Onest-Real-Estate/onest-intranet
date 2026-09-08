"""JSON request bodies must read exactly like the form post they replace.

Inertia sends `application/json` for any visit without a file. Django parses
`request.POST` only for form-encoded and multipart bodies, so before this
middleware every field of every Inertia mutation arrived empty — silently, with
no error to notice and no failing test, because the Django test client posts
form-encoded by default.

These tests therefore assert the *equivalence* that fifteen view modules now
rely on: what a view reads must not depend on how the caller encoded it.
"""

from __future__ import annotations

import json

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from apps.web.middleware import InertiaJsonPostMiddleware


def read(request) -> dict:
    """Whatever a view would see, captured through the middleware."""
    seen: dict = {}

    def view(req):
        seen["post"] = req.POST
        seen["files"] = req.FILES
        return HttpResponse()

    InertiaJsonPostMiddleware(view)(request)
    return seen


def post_json(payload, **extra):
    return RequestFactory().post(
        "/anything", data=json.dumps(payload), content_type="application/json", **extra
    )


def test_a_json_body_reaches_request_post():
    seen = read(post_json({"status": "in_progress", "note": "on it"}))
    assert seen["post"]["status"] == "in_progress"
    assert seen["post"]["note"] == "on it"


def test_a_list_survives_as_a_list():
    """The reason a client-side `FormData` switch could not have fixed this.

    Inertia writes an array into `FormData` as `order[0]`, `order[1]`, so
    `getlist("order")` returns nothing and a reorder silently does nothing.
    """
    seen = read(post_json({"order": ["3", "1", "2"]}))
    assert seen["post"].getlist("order") == ["3", "1", "2"]


def test_a_boolean_reads_as_the_checkbox_it_replaces():
    """Views test `== "1"`, which is what a checkbox and Inertia's own
    `FormData` serializer both send. `"True"` would fail every one of them."""
    seen = read(post_json({"internal": True, "pinned": False}))
    assert seen["post"]["internal"] == "1"
    assert seen["post"]["pinned"] == "0"


def test_null_reads_as_the_empty_field_a_browser_sends():
    seen = read(post_json({"assignee": None}))
    assert seen["post"]["assignee"] == ""


def test_numbers_arrive_as_strings():
    seen = read(post_json({"office": 7, "ratio": 1.5}))
    assert seen["post"]["office"] == "7"
    assert seen["post"]["ratio"] == "1.5"


def test_a_nested_object_is_handed_over_rather_than_dropped():
    seen = read(post_json({"audience": {"offices": [1, 2]}}))
    assert json.loads(seen["post"]["audience"]) == {"offices": [1, 2]}


def test_the_translated_post_is_immutable_like_a_real_one():
    seen = read(post_json({"a": "b"}))
    with pytest.raises(AttributeError):
        seen["post"]["a"] = "c"


def test_files_is_present_and_empty_rather_than_missing():
    seen = read(post_json({"a": "b"}))
    assert len(seen["files"]) == 0


def test_a_form_encoded_post_is_left_alone():
    request = RequestFactory().post("/anything", {"status": "open"})
    assert read(request)["post"]["status"] == "open"


def test_a_get_is_never_touched():
    request = RequestFactory().get("/anything", {"q": "term"})
    seen = read(request)
    assert seen["post"] == {}
    # The query string is where a GET's data lives, and it still is.
    assert request.GET["q"] == "term"


def test_a_malformed_body_leaves_post_empty_rather_than_raising():
    """A view answering its own validation error beats a 500."""
    request = RequestFactory().post(
        "/anything", data="{not json", content_type="application/json"
    )
    assert read(request)["post"] == {}


def test_a_bare_list_body_has_no_field_names_to_read():
    assert read(post_json(["a", "b"]))["post"] == {}


def test_an_empty_body_is_not_an_error():
    request = RequestFactory().post(
        "/anything", data="", content_type="application/json"
    )
    assert read(request)["post"] == {}


def test_a_multipart_upload_keeps_djangos_own_parser():
    """Files must never be routed through the JSON path."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    request = RequestFactory().post(
        "/anything",
        {"file": SimpleUploadedFile("a.log", b"x"), "internal": "1"},
    )
    seen = read(request)
    assert seen["post"]["internal"] == "1"
    assert seen["files"]["file"].name == "a.log"
