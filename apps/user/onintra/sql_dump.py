"""Parse phpMyAdmin-style MariaDB INSERT dumps into row dictionaries."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_INSERT_HEADER = re.compile(
    r"INSERT\s+INTO\s+`(?P<table>[^`]+)`\s*\((?P<columns>[^)]+)\)\s*VALUES\s*",
    re.IGNORECASE,
)


def load_dump_tables(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    """Return ``{table_name: [row_dict, ...]}`` from a SQL dump file."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    tables: dict[str, list[dict[str, Any]]] = {}
    index = 0
    while True:
        match = _INSERT_HEADER.search(text, index)
        if match is None:
            break
        table = match.group("table")
        columns = [
            column.strip().strip("`") for column in match.group("columns").split(",")
        ]
        values_start = match.end()
        tuples, next_index = _parse_value_tuples(text, values_start)
        rows = [dict(zip(columns, values, strict=True)) for values in tuples]
        tables.setdefault(table, []).extend(rows)
        index = next_index
    return tables


def _parse_value_tuples(text: str, start: int) -> tuple[list[tuple[Any, ...]], int]:
    tuples: list[tuple[Any, ...]] = []
    index = start
    length = len(text)

    while index < length:
        index = _skip_ws_and_commas(text, index)
        if index >= length or text[index] != "(":
            break
        values, index = _parse_tuple(text, index)
        tuples.append(values)

    index = _skip_ws(text, index)
    if index < length and text[index] == ";":
        index += 1
    return tuples, index


def _parse_tuple(text: str, start: int) -> tuple[tuple[Any, ...], int]:
    assert text[start] == "("
    index = start + 1
    values: list[Any] = []
    length = len(text)

    while index < length:
        index = _skip_ws_and_commas(text, index)
        if index >= length:
            raise ValueError("Unterminated SQL value tuple.")
        if text[index] == ")":
            return tuple(values), index + 1
        value, index = _parse_value(text, index)
        values.append(value)

    raise ValueError("Unterminated SQL value tuple.")


def _parse_value(text: str, start: int) -> tuple[Any, int]:
    index = _skip_ws(text, start)
    if index >= len(text):
        raise ValueError("Unexpected end of SQL value list.")

    char = text[index]
    if char == "'":
        return _parse_string(text, index)
    if char == "(":
        nested, index = _parse_tuple(text, index)
        return nested, index
    if text.startswith("NULL", index):
        return None, index + 4
    return _parse_bare_token(text, index)


def _parse_string(text: str, start: int) -> tuple[str, int]:
    assert text[start] == "'"
    index = start + 1
    parts: list[str] = []
    length = len(text)

    while index < length:
        char = text[index]
        if char == "'":
            if index + 1 < length and text[index + 1] == "'":
                parts.append("'")
                index += 2
                continue
            return "".join(parts), index + 1
        if char == "\\":
            index += 1
            if index >= length:
                break
            escape = text[index]
            parts.append(_UNESCAPE.get(escape, escape))
            index += 1
            continue
        parts.append(char)
        index += 1

    raise ValueError("Unterminated SQL string literal.")


def _parse_bare_token(text: str, start: int) -> tuple[Any, int]:
    index = start
    length = len(text)
    while index < length and text[index] not in ",)":
        index += 1
    token = text[start:index].strip()
    if not token:
        raise ValueError("Empty SQL value token.")
    if re.fullmatch(r"-?\d+", token):
        return int(token), index
    if re.fullmatch(r"-?\d+\.\d+", token):
        return float(token), index
    return token, index


def _skip_ws(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _skip_ws_and_commas(text: str, index: int) -> int:
    while index < len(text) and (text[index].isspace() or text[index] == ","):
        index += 1
    return index


_UNESCAPE = {
    "0": "\0",
    "b": "\b",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "Z": "\x1a",
    "'": "'",
    '"': '"',
    "\\": "\\",
}
