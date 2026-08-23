"""The approved body representation, and the reasons it is safe.

The argument these tests defend is *structural*, not diligent: unsafe markup is
never interpreted, so there is no allowlist to keep ahead of. A ``<script>``
comes back as the characters an author typed, inside a ``text`` span, and the
renderer has no code path that could do anything else with it.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from apps.announcements.richtext import (
    ALLOWED_SCHEMES,
    MAX_BLOCKS,
    body_payload,
    parse_body,
    parse_inline,
    safe_url,
    unsafe_links,
    validate_url,
)


def texts(blocks) -> list[str]:
    """Every rendered character, block order preserved."""
    out: list[str] = []
    for block in blocks:
        for span in block.get("spans", []):
            out.append(span["value"])
        for item in block.get("items", []):
            out.extend(span["value"] for span in item)
    return out


# --------------------------------------------------------------------------- #
# Nothing is ever markup
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "hostile",
    [
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        "<iframe src='https://evil.test'></iframe>",
        "<object data='x'></object>",
        "<svg/onload=alert(1)>",
        "<a href='javascript:alert(1)'>click</a>",
        "<style>body{display:none}</style>",
        "<!-- <script> -->",
    ],
)
def test_html_is_never_markup_only_characters(hostile):
    """The whole security argument, one case per shape people try."""
    blocks = parse_body(hostile)

    assert len(blocks) == 1
    assert blocks[0]["type"] == "paragraph"
    # It survives verbatim as text — not stripped, not escaped-then-unescaped,
    # simply never treated as markup.
    assert "".join(texts(blocks)) == hostile
    # And nothing anywhere in the tree carries a destination.
    assert all(
        span.get("type") != "link"
        for block in blocks
        for span in block.get("spans", [])
    )


def test_no_block_or_span_type_outside_the_grammar_can_be_produced():
    """A renderer only has to handle four block types and four span types."""
    blocks = parse_body(
        "## Heading\n\ntext **bold** *italic* [link](https://a.test)\n\n"
        "- one\n- two\n\n1. first\n\n> quoted"
    )
    assert {block["type"] for block in blocks} <= {
        "paragraph",
        "heading",
        "list",
        "quote",
    }
    span_types = {
        span["type"]
        for block in blocks
        for span in [
            *block.get("spans", []),
            *(s for i in block.get("items", []) for s in i),
        ]
    }
    assert span_types <= {"text", "strong", "em", "link"}


# --------------------------------------------------------------------------- #
# URLs
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "hostile",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "java\tscript:alert(1)",
        "java\nscript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "vbscript:msgbox(1)",
        "file:///etc/passwd",
        "http://cleartext.test",
        "//evil.test/path",
        "ftp://files.test",
        "",
        "   ",
        "not a url",
    ],
)
def test_unsafe_schemes_are_refused(hostile):
    assert safe_url(hostile) is None


@pytest.mark.parametrize(
    "accepted",
    [
        "https://onest.test/policy",
        "mailto:compliance@onest.test",
        "/operations/announcements",
    ],
)
def test_safe_destinations_are_accepted(accepted):
    assert safe_url(accepted) == accepted


def test_cleartext_http_is_refused_deliberately():
    """Not an oversight: sending the brokerage to a cleartext page is a
    downgrade, and every internal tool is already TLS."""
    assert "http" not in ALLOWED_SCHEMES
    assert safe_url("http://intranet.test") is None


def test_a_refused_link_renders_as_words_not_as_a_link():
    blocks = parse_body("Read [the policy](javascript:alert(1)) today.")

    spans = blocks[0]["spans"]
    assert all(span["type"] == "text" for span in spans)
    assert "the policy" in "".join(span["value"] for span in spans)


def test_a_permitted_link_keeps_its_destination():
    blocks = parse_body("Read [the policy](https://onest.test/p) today.")

    link = next(span for span in blocks[0]["spans"] if span["type"] == "link")
    assert link == {
        "type": "link",
        "value": "the policy",
        "href": "https://onest.test/p",
    }


def test_validate_url_raises_for_the_field_it_was_given():
    with pytest.raises(ValidationError) as caught:
        validate_url("javascript:alert(1)", field="cta_url")
    assert "cta_url" in caught.value.message_dict


def test_unsafe_links_reports_what_an_author_should_fix():
    assert unsafe_links(
        "[a](https://ok.test) [b](javascript:x) [c](http://plain.test)"
    ) == ["javascript:x", "http://plain.test"]


# --------------------------------------------------------------------------- #
# The grammar
# --------------------------------------------------------------------------- #


def test_paragraphs_split_on_blank_lines_and_join_wrapped_lines():
    blocks = parse_body("one\nstill one\n\ntwo")

    assert [block["type"] for block in blocks] == ["paragraph", "paragraph"]
    assert texts(blocks[:1]) == ["one still one"]


def test_headings_stop_at_the_documented_depth():
    blocks = parse_body("## two\n\n### three\n\n#### four")

    assert [block.get("level") for block in blocks[:2]] == [2, 3]
    # Deeper is not structure — it is the characters the author typed.
    assert blocks[2]["type"] == "paragraph"
    assert texts(blocks[2:]) == ["#### four"]


def test_consecutive_bullets_make_one_list_and_a_switch_starts_another():
    blocks = parse_body("- a\n- b\n1. c")

    assert [block["type"] for block in blocks] == ["list", "list"]
    assert blocks[0]["ordered"] is False
    assert len(blocks[0]["items"]) == 2
    assert blocks[1]["ordered"] is True


def test_quotes_and_emphasis_round_trip():
    blocks = parse_body("> **loud** and *quiet*")

    assert blocks[0]["type"] == "quote"
    assert [span["type"] for span in blocks[0]["spans"]] == [
        "strong",
        "text",
        "em",
    ]


def test_malformed_markup_degrades_to_the_characters_typed():
    """An unclosed marker must not swallow the rest of the notice."""
    blocks = parse_body("**unclosed and [broken](")

    assert "".join(texts(blocks)) == "**unclosed and [broken]("


def test_an_empty_body_is_no_blocks_rather_than_an_empty_paragraph():
    assert parse_body("") == []
    assert parse_body("   \n\n  ") == []


def test_a_runaway_body_is_bounded():
    blocks = parse_body("\n\n".join(str(index) for index in range(MAX_BLOCKS + 50)))
    assert len(blocks) == MAX_BLOCKS


def test_parse_inline_never_returns_nothing_for_real_text():
    assert parse_inline("plain") == [{"type": "text", "value": "plain"}]


def test_body_payload_is_plain_dicts_for_an_inertia_prop():
    payload = body_payload("## Title\n\ntext")
    assert isinstance(payload, list)
    assert all(isinstance(block, dict) for block in payload)
