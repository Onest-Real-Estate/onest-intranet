"""The approved rich-text representation for announcement bodies.

The decision, stated once
-------------------------
An announcement body is **a restricted plain-text markup source**, and it is
delivered to the browser as a **structured block tree**, never as HTML.

There is no HTML pipeline here at all — no parser, no sanitizer allowlist, no
``dangerouslySetInnerHTML`` on the other end. That is the whole security
argument, and it is structural rather than diligent: a ``<script>`` in a body is
not "stripped", it is simply never interpreted as markup. It survives as the
literal characters an author typed, and React renders them as text, escaped,
because the payload says ``{"type": "text", "value": "<script>…"}``. The same
goes for ``<iframe>``, ``onclick=``, ``<object>``, and every tag anyone invents
after this file is written: none of them are in the grammar, so none of them
have a code path.

Sanitizing an allowlist of HTML is the usual approach and it is a permanent
maintenance liability — every parser quirk and mutation-XSS trick is a new bug
against your allowlist. Not accepting HTML has no such surface.

The grammar
-----------
Blocks, separated by blank lines:

=====================  ====================================================
``## text``            Heading (two or three hashes; deeper is literal text)
``- item``             Unordered list; consecutive lines make one list
``1. item``            Ordered list
``> text``             Quote
anything else          Paragraph
=====================  ====================================================

Inline, inside any block's text:

=====================  ====================================================
``**bold**``           Strong emphasis
``*italic*``           Emphasis
``[label](url)``       Link, **https / mailto / site-relative only**
=====================  ====================================================

Anything that does not match is literal text, including a stray ``*`` or an
unclosed bracket. Malformed markup degrades to what the author typed rather
than swallowing the rest of the document.

Links are the one place a value can carry a scheme, so they are the one place
that validates: :func:`safe_url` accepts ``https:``, ``mailto:``, and
site-relative paths, and refuses everything else — ``javascript:``, ``data:``,
``vbscript:``, ``file:``, bare ``http:``, and protocol-relative ``//host``
(which inherits the page's scheme and is a common bypass). The call to action
uses the same function, so there is one answer to "is this URL safe" rather
than two that can disagree.
"""

from __future__ import annotations

import re
from typing import Any, Literal, TypedDict

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

#: Schemes a link or a call to action may carry. ``http`` is deliberately
#: absent: an intranet notice that sends the whole brokerage to a cleartext
#: page is a downgrade nobody asked for, and every internal tool is TLS.
ALLOWED_SCHEMES: frozenset[str] = frozenset({"https", "mailto"})

#: How deep a heading may go. Anything more is literal text — a body is a
#: notice, not a document with six levels of structure.
MAX_HEADING_LEVEL = 3

#: Bound on one body's blocks. A runaway paste cannot turn one announcement
#: into a payload that costs every reader's feed render.
MAX_BLOCKS = 400

_HEADING = re.compile(r"^(#{2,6})\s+(.*)$")
_UNORDERED = re.compile(r"^[-*]\s+(.*)$")
_ORDERED = re.compile(r"^\d+[.)]\s+(.*)$")
_QUOTE = re.compile(r"^>\s?(.*)$")
_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
_STRONG = re.compile(r"\*\*([^*\n]+)\*\*")
_EM = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")


class InlineNode(TypedDict, total=False):
    type: Literal["text", "strong", "em", "link"]
    value: str
    href: str


class Block(TypedDict, total=False):
    type: Literal["paragraph", "heading", "list", "quote"]
    level: int
    ordered: bool
    spans: list[InlineNode]
    items: list[list[InlineNode]]


# --------------------------------------------------------------------------- #
# URLs
# --------------------------------------------------------------------------- #


def safe_url(raw: str) -> str | None:
    """Return the URL if it is one we will hand a reader, else ``None``.

    Deliberately allowlist-shaped: an unrecognised value is refused rather than
    guessed at. A site-relative path (``/operations/...``) is allowed because it
    cannot leave the hub and carries no scheme to abuse; a protocol-relative
    ``//host`` is refused precisely because it looks relative and is not.
    """
    value = (raw or "").strip()
    if not value or any(char.isspace() for char in value):
        return None
    # Control characters are how ``java\tscript:`` slips past a naive check.
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        return None
    if value.startswith("//"):
        return None
    if value.startswith("/"):
        return value
    scheme, separator, rest = value.partition(":")
    if not separator or not rest:
        return None
    if scheme.lower() not in ALLOWED_SCHEMES:
        return None
    return value


def validate_url(raw: str, *, field: str) -> str:
    """``safe_url`` as a form/model validator."""
    resolved = safe_url(raw)
    if resolved is None:
        raise ValidationError(
            {
                field: _(
                    "Use an https:// address, a mailto: address, or a link "
                    "inside the hub starting with /."
                )
            }
        )
    return resolved


# --------------------------------------------------------------------------- #
# Inline
# --------------------------------------------------------------------------- #


def _text(value: str) -> InlineNode:
    return {"type": "text", "value": value}


def parse_inline(source: str) -> list[InlineNode]:
    """One line of text as a flat span list.

    Flat rather than nested on purpose: a link inside bold inside a quote is
    more structure than a notice needs, and every level of nesting is another
    shape the renderer has to be trusted to handle. One pass, three patterns,
    no recursion.
    """
    if not source:
        return []
    spans: list[InlineNode] = []
    index = 0
    for match in re.finditer(
        f"{_LINK.pattern}|{_STRONG.pattern}|{_EM.pattern}", source
    ):
        if match.start() > index:
            spans.append(_text(source[index : match.start()]))
        label, href, strong, emphasis = match.groups()
        if label is not None:
            resolved = safe_url(href or "")
            if resolved is None:
                # An unsafe link is shown as the words the author wrote, with no
                # destination. Dropping it silently would hide that a link was
                # ever intended; rendering it would be the bug.
                spans.append(_text(label))
            else:
                spans.append({"type": "link", "value": label, "href": resolved})
        elif strong is not None:
            spans.append({"type": "strong", "value": strong})
        else:
            spans.append({"type": "em", "value": emphasis})
        index = match.end()
    if index < len(source):
        spans.append(_text(source[index:]))
    return spans or [_text(source)]


# --------------------------------------------------------------------------- #
# Blocks
# --------------------------------------------------------------------------- #


def parse_body(source: str) -> list[Block]:
    """The body as a block tree the frontend renders with real elements.

    Never raises. A body that is empty, whitespace, or entirely unrecognised
    yields the paragraphs an author would expect, because everything the
    grammar does not claim is a paragraph.
    """
    blocks: list[Block] = []
    lines = (source or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    paragraph: list[str] = []
    list_items: list[str] = []
    list_ordered = False
    quote: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            blocks.append(
                {"type": "paragraph", "spans": parse_inline(" ".join(paragraph))}
            )
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            blocks.append(
                {
                    "type": "list",
                    "ordered": list_ordered,
                    "items": [parse_inline(item) for item in list_items],
                }
            )
            list_items = []

    def flush_quote() -> None:
        nonlocal quote
        if quote:
            blocks.append({"type": "quote", "spans": parse_inline(" ".join(quote))})
            quote = []

    def flush_all() -> None:
        flush_paragraph()
        flush_list()
        flush_quote()

    for raw_line in lines:
        if len(blocks) >= MAX_BLOCKS:
            break
        line = raw_line.rstrip()
        if not line.strip():
            flush_all()
            continue

        heading = _HEADING.match(line)
        if heading:
            flush_all()
            level = len(heading.group(1))
            if level > MAX_HEADING_LEVEL:
                # Too deep to be structure; treat the hashes as the text they
                # literally are rather than inventing an <h6>.
                paragraph.append(line)
                continue
            blocks.append(
                {
                    "type": "heading",
                    "level": level,
                    "spans": parse_inline(heading.group(2)),
                }
            )
            continue

        ordered = _ORDERED.match(line)
        unordered = _UNORDERED.match(line)
        if ordered or unordered:
            flush_paragraph()
            flush_quote()
            wants_ordered = ordered is not None
            if list_items and wants_ordered != list_ordered:
                flush_list()
            list_ordered = wants_ordered
            match = ordered or unordered
            assert match is not None
            list_items.append(match.group(1))
            continue

        quoted = _QUOTE.match(line)
        if quoted:
            flush_paragraph()
            flush_list()
            quote.append(quoted.group(1))
            continue

        flush_list()
        flush_quote()
        paragraph.append(line)

    flush_all()
    return blocks[:MAX_BLOCKS]


def body_payload(source: str) -> list[dict[str, Any]]:
    """``parse_body`` as plain dicts for an Inertia prop."""
    return [dict(block) for block in parse_body(source)]


def unsafe_links(source: str) -> list[str]:
    """Link destinations in a body that would be refused, for validation.

    Reported rather than silently downgraded at *authoring* time: an author who
    pasted a ``http://`` link should be told, even though the renderer would
    have degraded it to plain text safely anyway.
    """
    found: list[str] = []
    for match in _LINK.finditer(source or ""):
        href = match.group(2)
        if safe_url(href) is None:
            found.append(href)
    return found
