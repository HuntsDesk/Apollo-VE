"""
Markdown → Google Docs batchUpdate request builder.

Parses a markdown string and emits a list of Google Docs API batchUpdate
requests that, when applied starting at a given document index, produce
native Docs formatting (headings, bold, italic, bullet lists, numbered
lists) rather than raw markdown text.

Supported markdown:
    # H1          -> HEADING_1
    ## H2         -> HEADING_2
    ### H3        -> HEADING_3
    - item        -> bulleted list (BULLET_DISC_CIRCLE_SQUARE)
    1. item       -> numbered list (NUMBERED_DECIMAL_ALPHA_ROMAN)
    **bold**      -> bold text run
    *italic*      -> italic text run

Usage:
    requests = markdown_to_docs_requests(markdown, start_index=1)
    service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()

Notes:
    - Requests must be applied in the returned order. Insertions come first,
      then paragraph/bullet styling, then inline text styles.
    - Indices account for the cumulative length of inserted text.
    - A single trailing newline per block is included in the insert so
      each block becomes its own paragraph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\s*\d+\.\s+(.*)$")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")


@dataclass
class _InlineRange:
    """A range within a paragraph that needs inline text styling."""

    start_offset: int  # offset within the paragraph's text (0-based)
    end_offset: int
    style: Dict[str, Any]
    fields: str


@dataclass
class _Block:
    """A parsed markdown block (paragraph)."""

    text: str  # plain text, without markdown markers
    named_style_type: Optional[str] = None  # e.g., HEADING_1
    bullet_preset: Optional[str] = None  # e.g., BULLET_DISC_CIRCLE_SQUARE
    inline_ranges: List[_InlineRange] = field(default_factory=list)


def _parse_inline(text: str) -> Tuple[str, List[_InlineRange]]:
    """
    Strip inline markdown from text and return (plain_text, inline_ranges).

    Processes bold (`**x**`) first, then italic (`*x*`).
    Offsets are computed against the resulting plain_text.
    """
    ranges: List[_InlineRange] = []
    # Pass 1: bold
    result: List[str] = []
    cursor = 0
    plain_offset = 0
    for match in _BOLD_RE.finditer(text):
        # Append text before match
        before = text[cursor : match.start()]
        result.append(before)
        plain_offset += len(before)
        inner = match.group(1)
        start = plain_offset
        result.append(inner)
        plain_offset += len(inner)
        ranges.append(
            _InlineRange(start, plain_offset, {"bold": True}, "bold")
        )
        cursor = match.end()
    result.append(text[cursor:])
    after_bold = "".join(result)

    # Pass 2: italic — need to adjust the existing bold ranges' offsets
    result2: List[str] = []
    cursor = 0
    plain_offset = 0
    offset_shifts: List[Tuple[int, int]] = []  # (position, shift)
    italic_ranges: List[_InlineRange] = []
    for match in _ITALIC_RE.finditer(after_bold):
        before = after_bold[cursor : match.start()]
        result2.append(before)
        plain_offset += len(before)
        inner = match.group(1)
        start = plain_offset
        result2.append(inner)
        plain_offset += len(inner)
        italic_ranges.append(
            _InlineRange(start, plain_offset, {"italic": True}, "italic")
        )
        # Each italic match removes 2 chars (the two *) from positions >= match.start()
        offset_shifts.append((match.start(), 2))
        cursor = match.end()
    result2.append(after_bold[cursor:])
    plain_text = "".join(result2)

    # Shift existing bold ranges to account for italic markers removed
    def shift(pos: int) -> int:
        total = 0
        for orig_pos, amount in offset_shifts:
            if orig_pos < pos:
                total += amount
        return pos - total

    shifted: List[_InlineRange] = []
    for r in ranges:
        shifted.append(
            _InlineRange(shift(r.start_offset), shift(r.end_offset), r.style, r.fields)
        )
    shifted.extend(italic_ranges)
    shifted.sort(key=lambda r: r.start_offset)
    return plain_text, shifted


def _parse_blocks(markdown: str) -> List[_Block]:
    """Split markdown into blocks, one per non-empty line."""
    blocks: List[_Block] = []
    for raw_line in markdown.split("\n"):
        line = raw_line.rstrip()
        if not line:
            # Preserve empty lines as empty paragraphs
            blocks.append(_Block(text=""))
            continue
        heading = _HEADING_RE.match(line)
        bullet = _BULLET_RE.match(line)
        numbered = _NUMBERED_RE.match(line)
        if heading:
            level = len(heading.group(1))
            inner, inline = _parse_inline(heading.group(2))
            blocks.append(
                _Block(
                    text=inner,
                    named_style_type=f"HEADING_{level}",
                    inline_ranges=inline,
                )
            )
        elif bullet:
            inner, inline = _parse_inline(bullet.group(1))
            blocks.append(
                _Block(
                    text=inner,
                    bullet_preset="BULLET_DISC_CIRCLE_SQUARE",
                    inline_ranges=inline,
                )
            )
        elif numbered:
            inner, inline = _parse_inline(numbered.group(1))
            blocks.append(
                _Block(
                    text=inner,
                    bullet_preset="NUMBERED_DECIMAL_ALPHA_ROMAN",
                    inline_ranges=inline,
                )
            )
        else:
            inner, inline = _parse_inline(line)
            blocks.append(_Block(text=inner, inline_ranges=inline))
    return blocks


def markdown_to_docs_requests(
    markdown: str,
    start_index: int = 1,
    tab_id: Optional[str] = None,
    segment_id: Optional[str] = None,
    end_of_segment: bool = False,
) -> List[Dict[str, Any]]:
    """
    Convert a markdown string to Google Docs batchUpdate requests.

    Args:
        markdown: The markdown text to convert.
        start_index: Document index at which to begin inserting (default 1).
            Ignored if `end_of_segment=True`.
        tab_id: Optional tab ID to scope every location/range to.
        segment_id: Optional header/footer/footnote segment ID.
        end_of_segment: If True, the first insert goes to the end of the segment
            (no index needed). Subsequent formatting uses the positions the
            inserted text will occupy; this works only for an empty segment or
            requires a preliminary inspect_doc_structure call otherwise. Most
            reliable usage: a fresh empty segment/body.

    Returns:
        List of batchUpdate request dicts, in the order: insertText, then
        paragraph style, then bullet preset, then inline text style requests.
    """
    if not markdown:
        return []

    blocks = _parse_blocks(markdown)

    combined_parts: List[str] = []
    block_ranges: List[Tuple[int, int]] = []
    cursor = start_index
    for block in blocks:
        text_with_newline = block.text + "\n"
        block_start = cursor
        block_end = cursor + len(block.text)
        block_ranges.append((block_start, block_end))
        combined_parts.append(text_with_newline)
        cursor += len(text_with_newline)

    combined_text = "".join(combined_parts)

    def _with_tab(d: Dict[str, Any]) -> Dict[str, Any]:
        if tab_id:
            d["tabId"] = tab_id
        return d

    # Build the initial insert
    if end_of_segment:
        insert_location: Dict[str, Any] = {
            "endOfSegmentLocation": _with_tab(
                {"segmentId": segment_id} if segment_id else {}
            )
        }
    else:
        loc: Dict[str, Any] = {"index": start_index}
        if segment_id:
            loc["segmentId"] = segment_id
        insert_location = {"location": _with_tab(loc)}

    requests: List[Dict[str, Any]] = [
        {"insertText": {**insert_location, "text": combined_text}}
    ]

    for block, (b_start, b_end) in zip(blocks, block_ranges):
        if block.named_style_type:
            rng: Dict[str, Any] = {"startIndex": b_start, "endIndex": b_end + 1}
            if segment_id:
                rng["segmentId"] = segment_id
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": _with_tab(rng),
                        "paragraphStyle": {
                            "namedStyleType": block.named_style_type
                        },
                        "fields": "namedStyleType",
                    }
                }
            )

    for block, (b_start, b_end) in zip(blocks, block_ranges):
        if block.bullet_preset:
            rng = {"startIndex": b_start, "endIndex": b_end + 1}
            if segment_id:
                rng["segmentId"] = segment_id
            requests.append(
                {
                    "createParagraphBullets": {
                        "range": _with_tab(rng),
                        "bulletPreset": block.bullet_preset,
                    }
                }
            )

    for block, (b_start, _b_end) in zip(blocks, block_ranges):
        for ir in block.inline_ranges:
            if ir.end_offset <= ir.start_offset:
                continue
            rng = {
                "startIndex": b_start + ir.start_offset,
                "endIndex": b_start + ir.end_offset,
            }
            if segment_id:
                rng["segmentId"] = segment_id
            requests.append(
                {
                    "updateTextStyle": {
                        "range": _with_tab(rng),
                        "textStyle": ir.style,
                        "fields": ir.fields,
                    }
                }
            )

    return requests


def looks_like_markdown(text: str) -> bool:
    """
    Heuristic check: does this text contain any markdown features we'd convert?

    Currently unused by the tools (they rely on an explicit flag), but useful
    for future autodetection or logging.
    """
    if not text:
        return False
    if _HEADING_RE.search(text) or _BOLD_RE.search(text) or _ITALIC_RE.search(text):
        return True
    for line in text.split("\n"):
        if _BULLET_RE.match(line) or _NUMBERED_RE.match(line):
            return True
    return False
