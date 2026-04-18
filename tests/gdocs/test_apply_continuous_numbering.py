"""
Unit tests for apply_continuous_numbering — the net-new tool ported from
blakesplay/apollo (TypeScript → Python).

Verifies the pure-Python helpers (paragraph scan, sequence grouping, request
builder) without hitting the Google Docs API. End-to-end integration against
a real doc is a manual test.
"""

from typing import Any, Dict, List, Optional

import pytest

from gdocs.docs_tools import (
    _acn_scan_paragraphs,
    _acn_group_sequences,
    _acn_build_requests,
    _acn_is_numeric_list,
)


def _mk_text_run(
    text: str,
    italic: bool = False,
    bold: bool = False,
    start: Optional[int] = None,
    end: Optional[int] = None,
) -> Dict[str, Any]:
    style: Dict[str, Any] = {}
    if italic:
        style["italic"] = True
    if bold:
        style["bold"] = True
    run: Dict[str, Any] = {"textRun": {"content": text}}
    if style:
        run["textRun"]["textStyle"] = style
    if start is not None:
        run["startIndex"] = start
    if end is not None:
        run["endIndex"] = end
    return run


def _mk_paragraph(
    start: int,
    end: int,
    text: str,
    italic: bool = False,
    bullet_list_id: Optional[str] = None,
    bullet_level: int = 0,
    named_style: str = "NORMAL_TEXT",
) -> Dict[str, Any]:
    paragraph: Dict[str, Any] = {
        "elements": [_mk_text_run(text, italic=italic, start=start, end=end)],
        "paragraphStyle": {"namedStyleType": named_style},
    }
    if bullet_list_id is not None:
        paragraph["bullet"] = {
            "listId": bullet_list_id,
            "nestingLevel": bullet_level,
        }
    return {"startIndex": start, "endIndex": end, "paragraph": paragraph}


def _mk_paragraph_with_runs(
    start: int,
    end: int,
    runs: List[Dict[str, Any]],
    named_style: str = "NORMAL_TEXT",
) -> Dict[str, Any]:
    """Build a paragraph whose text is composed of pre-constructed runs."""
    return {
        "startIndex": start,
        "endIndex": end,
        "paragraph": {
            "elements": runs,
            "paragraphStyle": {"namedStyleType": named_style},
        },
    }


def test_is_numeric_list_detects_decimal():
    lists_map = {
        "list-a": {
            "listProperties": {
                "nestingLevels": [{"glyphType": "DECIMAL"}],
            }
        },
        "list-b": {
            "listProperties": {
                "nestingLevels": [{"glyphType": "GLYPH_TYPE_UNSPECIFIED"}],
            }
        },
    }
    assert _acn_is_numeric_list(lists_map, "list-a") is True
    assert _acn_is_numeric_list(lists_map, "list-b") is False
    assert _acn_is_numeric_list(lists_map, None) is False
    assert _acn_is_numeric_list(lists_map, "nonexistent") is False


def test_scan_paragraphs_classifies_step_prefix_and_italic_prompt():
    content = [
        _mk_paragraph(1, 12, "1. First step\n"),
        _mk_paragraph(12, 30, "prompt text italic\n", italic=True),
        _mk_paragraph(30, 42, "2. Second step\n"),
    ]
    paragraphs = _acn_scan_paragraphs(content, lists_map={})
    assert len(paragraphs) == 3
    assert paragraphs[0]["step_number"] == 1
    assert paragraphs[0]["prefix_len"] == 3  # "1. "
    assert paragraphs[0]["is_italic"] is False
    assert paragraphs[1]["step_number"] is None
    assert paragraphs[1]["is_italic"] is True
    assert paragraphs[2]["step_number"] == 2


def test_scan_paragraphs_detects_existing_numbered_list_for_idempotency():
    content = [
        _mk_paragraph(1, 12, "First step\n", bullet_list_id="list-num"),
        _mk_paragraph(12, 24, "Second step\n", bullet_list_id="list-num"),
    ]
    lists_map = {
        "list-num": {
            "listProperties": {"nestingLevels": [{"glyphType": "DECIMAL"}]}
        }
    }
    paragraphs = _acn_scan_paragraphs(content, lists_map)
    # No "N. " prefix but numbered_list_id is set — idempotency path.
    assert paragraphs[0]["step_number"] is None
    assert paragraphs[0]["numbered_list_id"] == "list-num"
    assert paragraphs[1]["numbered_list_id"] == "list-num"


def test_group_sequences_primary_path_starts_at_1():
    paragraphs = [
        {"start": 1, "end": 12, "text": "1. foo", "step_number": 1, "prefix_len": 3,
         "has_bullet": False, "numbered_list_id": None, "is_italic": False},
        {"start": 12, "end": 20, "text": "prompt", "step_number": None, "prefix_len": 0,
         "has_bullet": False, "numbered_list_id": None, "is_italic": False},
        {"start": 20, "end": 32, "text": "2. bar", "step_number": 2, "prefix_len": 3,
         "has_bullet": False, "numbered_list_id": None, "is_italic": False},
        {"start": 32, "end": 44, "text": "unrelated", "step_number": None, "prefix_len": 0,
         "has_bullet": False, "numbered_list_id": None, "is_italic": False},
    ]
    seqs = _acn_group_sequences(paragraphs)
    assert len(seqs) == 1
    assert len(seqs[0]) == 2  # just the two step paragraphs themselves
    assert seqs[0][0]["step_number"] == 1
    assert seqs[0][1]["step_number"] == 2


def test_group_sequences_multiple_sequences_separated_by_new_1():
    paragraphs = [
        {"start": 1, "end": 12, "text": "1. a", "step_number": 1, "prefix_len": 3,
         "has_bullet": False, "numbered_list_id": None, "is_italic": False},
        {"start": 12, "end": 24, "text": "2. b", "step_number": 2, "prefix_len": 3,
         "has_bullet": False, "numbered_list_id": None, "is_italic": False},
        {"start": 24, "end": 36, "text": "gap", "step_number": None, "prefix_len": 0,
         "has_bullet": False, "numbered_list_id": None, "is_italic": False},
        {"start": 36, "end": 48, "text": "1. c", "step_number": 1, "prefix_len": 3,
         "has_bullet": False, "numbered_list_id": None, "is_italic": False},
        {"start": 48, "end": 60, "text": "2. d", "step_number": 2, "prefix_len": 3,
         "has_bullet": False, "numbered_list_id": None, "is_italic": False},
    ]
    seqs = _acn_group_sequences(paragraphs)
    assert len(seqs) == 2
    assert len(seqs[0]) == 2
    assert len(seqs[1]) == 2


def test_group_sequences_fallback_by_list_id_for_idempotency():
    paragraphs = [
        {"start": 1, "end": 12, "text": "First", "step_number": None, "prefix_len": 0,
         "has_bullet": True, "numbered_list_id": "list-x", "is_italic": False},
        {"start": 12, "end": 24, "text": "Second", "step_number": None, "prefix_len": 0,
         "has_bullet": True, "numbered_list_id": "list-x", "is_italic": False},
    ]
    seqs = _acn_group_sequences(paragraphs)
    assert len(seqs) == 1
    assert len(seqs[0]) == 2


def test_build_requests_emits_expected_shape_for_simple_sequence():
    content = [
        _mk_paragraph(1, 13, "1. Step one\n"),
        _mk_paragraph(13, 25, "2. Step two\n"),
    ]
    paragraphs = _acn_scan_paragraphs(content, lists_map={})
    sequences = _acn_group_sequences(paragraphs)
    requests = _acn_build_requests(
        paragraphs, sequences, content, tab_id=None, strip_plain_text=True
    )

    # Must clear, then create, then per-step styling, then strip prefixes.
    kinds = [list(r.keys())[0] for r in requests]
    assert "deleteParagraphBullets" in kinds
    assert "createParagraphBullets" in kinds
    # Numbered bullet preset applied:
    create_reqs = [r for r in requests if "createParagraphBullets" in r]
    numbered = [
        r for r in create_reqs
        if r["createParagraphBullets"]["bulletPreset"] == "NUMBERED_DECIMAL_NESTED"
    ]
    assert len(numbered) >= 1
    # Prefix stripping at the END, in reverse order.
    strips = [r for r in requests if "deleteContentRange" in r]
    assert len(strips) == 2
    # Reverse-order: second step's prefix first.
    assert strips[0]["deleteContentRange"]["range"]["startIndex"] == 13
    assert strips[0]["deleteContentRange"]["range"]["endIndex"] == 16
    assert strips[1]["deleteContentRange"]["range"]["startIndex"] == 1
    assert strips[1]["deleteContentRange"]["range"]["endIndex"] == 4


def test_build_requests_strip_false_skips_prefix_deletions():
    content = [
        _mk_paragraph(1, 13, "1. Step one\n"),
    ]
    paragraphs = _acn_scan_paragraphs(content, lists_map={})
    sequences = _acn_group_sequences(paragraphs)
    requests = _acn_build_requests(
        paragraphs, sequences, content, tab_id=None, strip_plain_text=False
    )
    strips = [r for r in requests if "deleteContentRange" in r]
    assert len(strips) == 0


def test_build_requests_propagates_tab_id_to_every_range():
    content = [
        _mk_paragraph(1, 13, "1. Step one\n"),
        _mk_paragraph(13, 25, "2. Step two\n"),
    ]
    paragraphs = _acn_scan_paragraphs(content, lists_map={})
    sequences = _acn_group_sequences(paragraphs)
    requests = _acn_build_requests(
        paragraphs, sequences, content, tab_id="t.abc", strip_plain_text=True
    )
    # Every request must have its range scoped to tabId="t.abc".
    for r in requests:
        op = list(r.values())[0]
        rng = op.get("range")
        assert rng is not None
        assert rng.get("tabId") == "t.abc"


def test_build_requests_italic_prompt_gets_8pt_space_above():
    content = [
        _mk_paragraph(1, 13, "1. Step one\n"),
        _mk_paragraph(13, 30, "italic prompt\n", italic=True),
        _mk_paragraph(30, 42, "2. Step two\n"),
    ]
    paragraphs = _acn_scan_paragraphs(content, lists_map={})
    sequences = _acn_group_sequences(paragraphs)
    requests = _acn_build_requests(
        paragraphs, sequences, content, tab_id=None, strip_plain_text=True
    )
    # Find updateParagraphStyle on the italic prompt paragraph.
    prompt_styles = [
        r for r in requests
        if "updateParagraphStyle" in r
        and r["updateParagraphStyle"]["range"]["startIndex"] == 13
        and r["updateParagraphStyle"]["range"]["endIndex"] == 30
    ]
    assert prompt_styles, "italic prompt should get its own paragraph style request"
    ps = prompt_styles[0]["updateParagraphStyle"]["paragraphStyle"]
    assert ps["spaceAbove"]["magnitude"] == 8
    assert ps["spaceBelow"]["magnitude"] == 0
    assert ps["indentStart"]["magnitude"] == 36


def test_build_requests_non_italic_non_step_gets_0pt_space_above():
    content = [
        _mk_paragraph(1, 13, "1. Step one\n"),
        _mk_paragraph(13, 25, "plain text\n", italic=False),
        _mk_paragraph(25, 37, "2. Step two\n"),
    ]
    paragraphs = _acn_scan_paragraphs(content, lists_map={})
    sequences = _acn_group_sequences(paragraphs)
    requests = _acn_build_requests(
        paragraphs, sequences, content, tab_id=None, strip_plain_text=True
    )
    non_italic_styles = [
        r for r in requests
        if "updateParagraphStyle" in r
        and r["updateParagraphStyle"]["range"]["startIndex"] == 13
        and r["updateParagraphStyle"]["range"]["endIndex"] == 25
    ]
    assert non_italic_styles
    ps = non_italic_styles[0]["updateParagraphStyle"]["paragraphStyle"]
    assert ps["spaceAbove"]["magnitude"] == 0  # tight against the step above


def test_build_requests_each_step_gets_12pt_above_never_collapse():
    content = [
        _mk_paragraph(1, 13, "1. Step one\n"),
        _mk_paragraph(13, 25, "2. Step two\n"),
    ]
    paragraphs = _acn_scan_paragraphs(content, lists_map={})
    sequences = _acn_group_sequences(paragraphs)
    requests = _acn_build_requests(
        paragraphs, sequences, content, tab_id=None, strip_plain_text=True
    )
    # Find the per-step 12pt spacing styles.
    step_styles = []
    for r in requests:
        if "updateParagraphStyle" not in r:
            continue
        ps = r["updateParagraphStyle"]["paragraphStyle"]
        if ps.get("spacingMode") == "NEVER_COLLAPSE" and ps.get("spaceAbove", {}).get("magnitude") == 12:
            step_styles.append(r)
    assert len(step_styles) == 2  # one per step
    for s in step_styles:
        ps = s["updateParagraphStyle"]["paragraphStyle"]
        assert ps["spaceBelow"]["magnitude"] == 0
        assert ps["spacingMode"] == "NEVER_COLLAPSE"


def test_build_requests_flattens_mac_hanging_indent_on_normal_paragraphs():
    content = [
        _mk_paragraph(1, 30, "Preamble text outside sequence\n"),
        _mk_paragraph(30, 42, "1. Step one\n"),
        _mk_paragraph(42, 54, "2. Step two\n"),
        _mk_paragraph(54, 80, "Trailing text outside sequence\n"),
    ]
    paragraphs = _acn_scan_paragraphs(content, lists_map={})
    sequences = _acn_group_sequences(paragraphs)
    requests = _acn_build_requests(
        paragraphs, sequences, content, tab_id=None, strip_plain_text=True
    )
    # Look for indentStart=0, indentFirstLine=0 on the outside-span paragraphs.
    flat_indents = []
    for r in requests:
        if "updateParagraphStyle" not in r:
            continue
        ps = r["updateParagraphStyle"]["paragraphStyle"]
        if (
            ps.get("indentStart", {}).get("magnitude") == 0
            and ps.get("indentFirstLine", {}).get("magnitude") == 0
        ):
            flat_indents.append(r)
    # Both outside-span paragraphs (preamble + trailing) get flattened.
    assert len(flat_indents) == 2


def test_build_requests_skips_headings_in_flatten_pass():
    content = [
        _mk_paragraph(1, 30, "My heading\n", named_style="HEADING_1"),
        _mk_paragraph(30, 42, "1. Step one\n"),
        _mk_paragraph(42, 54, "2. Step two\n"),
    ]
    paragraphs = _acn_scan_paragraphs(content, lists_map={})
    sequences = _acn_group_sequences(paragraphs)
    requests = _acn_build_requests(
        paragraphs, sequences, content, tab_id=None, strip_plain_text=True
    )
    # No flatten-indent request should target the heading (start=1).
    flatten_targeting_heading = [
        r for r in requests
        if "updateParagraphStyle" in r
        and r["updateParagraphStyle"]["range"]["startIndex"] == 1
        and r["updateParagraphStyle"]["paragraphStyle"].get("indentStart", {}).get("magnitude") == 0
        and r["updateParagraphStyle"]["paragraphStyle"].get("indentFirstLine", {}).get("magnitude") == 0
    ]
    assert len(flatten_targeting_heading) == 0


def test_build_requests_applies_google_sans_per_run_preserving_bold():
    """Block (e): Google Sans per-run. MUST preserve each run's bold flag."""
    bold_run = _mk_text_run("Heading-like", bold=True, start=1, end=13)
    normal_run = _mk_text_run(" normal text\n", start=13, end=25)
    italic_run = _mk_text_run("italic", italic=True, start=25, end=32)
    content = [
        _mk_paragraph_with_runs(1, 32, [bold_run, normal_run, italic_run]),
        _mk_paragraph(32, 44, "1. Step one\n"),
        _mk_paragraph(44, 56, "2. Step two\n"),
    ]
    paragraphs = _acn_scan_paragraphs(content, lists_map={})
    sequences = _acn_group_sequences(paragraphs)
    requests = _acn_build_requests(
        paragraphs, sequences, content, tab_id=None, strip_plain_text=True
    )

    # Collect all Google Sans font-family requests.
    google_sans = [
        r for r in requests
        if "updateTextStyle" in r
        and r["updateTextStyle"]["textStyle"].get("weightedFontFamily", {}).get("fontFamily")
        == "Google Sans"
    ]
    assert google_sans, "expected Google Sans pass"

    # Bold run should set weight=700 + bold=True.
    bold_reqs = [
        r for r in google_sans
        if r["updateTextStyle"]["range"]["startIndex"] == 1
        and r["updateTextStyle"]["range"]["endIndex"] == 13
    ]
    assert bold_reqs
    ts = bold_reqs[0]["updateTextStyle"]["textStyle"]
    assert ts["weightedFontFamily"]["weight"] == 700
    assert ts["bold"] is True

    # Normal run should set weight=400 + bold=False.
    normal_reqs = [
        r for r in google_sans
        if r["updateTextStyle"]["range"]["startIndex"] == 13
        and r["updateTextStyle"]["range"]["endIndex"] == 25
    ]
    assert normal_reqs
    ts = normal_reqs[0]["updateTextStyle"]["textStyle"]
    assert ts["weightedFontFamily"]["weight"] == 400
    assert ts["bold"] is False


def test_build_requests_gives_title_and_heading_1_space_below():
    """Block (d3): TITLE and HEADING_1 get 12pt spaceBelow."""
    content = [
        _mk_paragraph(1, 20, "Document Title\n", named_style="TITLE"),
        _mk_paragraph(20, 35, "Section one\n", named_style="HEADING_1"),
        _mk_paragraph(35, 47, "1. Step one\n"),
        _mk_paragraph(47, 59, "2. Step two\n"),
    ]
    paragraphs = _acn_scan_paragraphs(content, lists_map={})
    sequences = _acn_group_sequences(paragraphs)
    requests = _acn_build_requests(
        paragraphs, sequences, content, tab_id=None, strip_plain_text=True
    )

    title_space = [
        r for r in requests
        if "updateParagraphStyle" in r
        and r["updateParagraphStyle"]["range"]["startIndex"] == 1
        and r["updateParagraphStyle"]["paragraphStyle"].get("spaceBelow", {}).get("magnitude") == 12
    ]
    h1_space = [
        r for r in requests
        if "updateParagraphStyle" in r
        and r["updateParagraphStyle"]["range"]["startIndex"] == 20
        and r["updateParagraphStyle"]["paragraphStyle"].get("spaceBelow", {}).get("magnitude") == 12
    ]
    assert len(title_space) == 1
    assert len(h1_space) == 1


def test_build_requests_heading_2_does_not_get_title_space_below():
    """Block (d3) is TITLE + HEADING_1 only. HEADING_2+ use markdown spacing."""
    content = [
        _mk_paragraph(1, 20, "Sub-section\n", named_style="HEADING_2"),
        _mk_paragraph(20, 32, "1. Step one\n"),
        _mk_paragraph(32, 44, "2. Step two\n"),
    ]
    paragraphs = _acn_scan_paragraphs(content, lists_map={})
    sequences = _acn_group_sequences(paragraphs)
    requests = _acn_build_requests(
        paragraphs, sequences, content, tab_id=None, strip_plain_text=True
    )

    h2_with_title_below = [
        r for r in requests
        if "updateParagraphStyle" in r
        and r["updateParagraphStyle"]["range"]["startIndex"] == 1
        and r["updateParagraphStyle"]["paragraphStyle"].get("spaceBelow", {}).get("magnitude") == 12
    ]
    assert h2_with_title_below == []


def test_build_requests_outside_span_body_gets_11pt_font():
    """Block (d2) includes 11pt font update on outside-span NORMAL_TEXT paragraphs."""
    content = [
        _mk_paragraph(1, 30, "Topmatter: what you'll learn\n"),
        _mk_paragraph(30, 42, "1. Step one\n"),
        _mk_paragraph(42, 54, "2. Step two\n"),
    ]
    paragraphs = _acn_scan_paragraphs(content, lists_map={})
    sequences = _acn_group_sequences(paragraphs)
    requests = _acn_build_requests(
        paragraphs, sequences, content, tab_id=None, strip_plain_text=True
    )

    topmatter_11pt = [
        r for r in requests
        if "updateTextStyle" in r
        and r["updateTextStyle"]["range"]["startIndex"] == 1
        and r["updateTextStyle"]["range"]["endIndex"] == 30
        and r["updateTextStyle"]["textStyle"].get("fontSize", {}).get("magnitude") == 11
    ]
    assert len(topmatter_11pt) >= 1


def test_build_requests_reapplies_disc_bullets_to_originally_bulleted_non_steps():
    content = [
        _mk_paragraph(1, 13, "1. Step\n"),
        _mk_paragraph(13, 25, "sub item\n", bullet_list_id="disc-list", bullet_level=0),
        _mk_paragraph(25, 37, "sub item 2\n", bullet_list_id="disc-list", bullet_level=0),
        _mk_paragraph(37, 49, "2. Step\n"),
    ]
    paragraphs = _acn_scan_paragraphs(content, lists_map={})
    # disc-list has no DECIMAL glyph, so it's not idempotent-list detected;
    # it just has has_bullet=True. Verify grouping + disc reapply.
    sequences = _acn_group_sequences(paragraphs)
    requests = _acn_build_requests(
        paragraphs, sequences, content, tab_id=None, strip_plain_text=True
    )
    disc_bullets = [
        r for r in requests
        if "createParagraphBullets" in r
        and r["createParagraphBullets"]["bulletPreset"] == "BULLET_DISC_CIRCLE_SQUARE"
    ]
    # One disc re-apply for the contiguous run 13-37.
    assert len(disc_bullets) == 1
    assert disc_bullets[0]["createParagraphBullets"]["range"]["startIndex"] == 13
    assert disc_bullets[0]["createParagraphBullets"]["range"]["endIndex"] == 37
