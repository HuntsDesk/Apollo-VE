"""Unit tests for gdocs.docs_markdown_writer.markdown_to_docs_requests."""

from gdocs.docs_markdown_writer import (
    looks_like_markdown,
    markdown_to_docs_requests,
)


def _insert_text(requests):
    return next(r for r in requests if "insertText" in r)


def _find(requests, key):
    return [r[key] for r in requests if key in r]


def test_empty_input_produces_no_requests():
    assert markdown_to_docs_requests("") == []


def test_plain_text_single_paragraph():
    requests = markdown_to_docs_requests("hello world", start_index=1)
    assert len(requests) == 1
    assert _insert_text(requests)["insertText"]["text"] == "hello world\n"
    assert _insert_text(requests)["insertText"]["location"]["index"] == 1


def test_heading_applies_named_style():
    requests = markdown_to_docs_requests("# Title", start_index=1)
    text_req = _insert_text(requests)["insertText"]
    assert text_req["text"] == "Title\n"
    para_styles = _find(requests, "updateParagraphStyle")
    assert len(para_styles) == 1
    assert para_styles[0]["paragraphStyle"]["namedStyleType"] == "HEADING_1"
    # range should cover "Title\n" -> indices 1..7
    assert para_styles[0]["range"]["startIndex"] == 1
    assert para_styles[0]["range"]["endIndex"] == 7


def test_three_heading_levels():
    requests = markdown_to_docs_requests("# A\n## B\n### C", start_index=1)
    styles = [
        s["paragraphStyle"]["namedStyleType"]
        for s in _find(requests, "updateParagraphStyle")
    ]
    assert styles == ["HEADING_1", "HEADING_2", "HEADING_3"]


def test_bold_generates_update_text_style():
    requests = markdown_to_docs_requests("hello **world** ok", start_index=1)
    text = _insert_text(requests)["insertText"]["text"]
    assert text == "hello world ok\n"
    text_styles = _find(requests, "updateTextStyle")
    assert len(text_styles) == 1
    assert text_styles[0]["textStyle"] == {"bold": True}
    # "world" starts at index 1 + len("hello ") = 7, ends at 12
    assert text_styles[0]["range"]["startIndex"] == 7
    assert text_styles[0]["range"]["endIndex"] == 12


def test_italic_generates_update_text_style():
    requests = markdown_to_docs_requests("hi *there*", start_index=1)
    assert _insert_text(requests)["insertText"]["text"] == "hi there\n"
    text_styles = _find(requests, "updateTextStyle")
    assert len(text_styles) == 1
    assert text_styles[0]["textStyle"] == {"italic": True}


def test_bold_and_italic_combined():
    requests = markdown_to_docs_requests("**b** and *i*", start_index=1)
    plain = _insert_text(requests)["insertText"]["text"]
    assert plain == "b and i\n"
    styles = _find(requests, "updateTextStyle")
    assert {"bold": True} in [s["textStyle"] for s in styles]
    assert {"italic": True} in [s["textStyle"] for s in styles]


def test_bullet_list():
    requests = markdown_to_docs_requests("- one\n- two", start_index=1)
    text = _insert_text(requests)["insertText"]["text"]
    assert text == "one\ntwo\n"
    bullets = _find(requests, "createParagraphBullets")
    assert len(bullets) == 2
    assert all(b["bulletPreset"] == "BULLET_DISC_CIRCLE_SQUARE" for b in bullets)


def test_numbered_list():
    requests = markdown_to_docs_requests("1. first\n2. second", start_index=1)
    bullets = _find(requests, "createParagraphBullets")
    assert len(bullets) == 2
    assert all(b["bulletPreset"] == "NUMBERED_DECIMAL_ALPHA_ROMAN" for b in bullets)


def test_mixed_document_structure():
    md = "# Title\nSome **bold** text\n- bullet one\n- bullet two\n1. step"
    requests = markdown_to_docs_requests(md, start_index=1)
    # Should have: 1 insert, 1 heading style, 2 bullet presets + 1 numbered preset, 1 bold style
    assert len(_find(requests, "updateParagraphStyle")) == 1
    assert len(_find(requests, "createParagraphBullets")) == 3
    text_styles = _find(requests, "updateTextStyle")
    assert len(text_styles) == 1
    assert text_styles[0]["textStyle"] == {"bold": True}


def test_start_index_offsets_correctly():
    requests = markdown_to_docs_requests("**x**", start_index=100)
    assert _insert_text(requests)["insertText"]["location"]["index"] == 100
    styles = _find(requests, "updateTextStyle")
    assert styles[0]["range"]["startIndex"] == 100
    assert styles[0]["range"]["endIndex"] == 101


def test_looks_like_markdown_detects_features():
    assert looks_like_markdown("# heading")
    assert looks_like_markdown("**bold**")
    assert looks_like_markdown("*italic*")
    assert looks_like_markdown("- list")
    assert looks_like_markdown("1. numbered")
    assert not looks_like_markdown("just plain text")
    assert not looks_like_markdown("")


def test_tab_id_propagates_to_all_locations_and_ranges():
    requests = markdown_to_docs_requests(
        "# Title\n**bold**\n- item", start_index=1, tab_id="t.abc"
    )
    # Every location/range should carry the tabId
    for r in requests:
        if "insertText" in r:
            assert r["insertText"]["location"]["tabId"] == "t.abc"
        if "updateParagraphStyle" in r:
            assert r["updateParagraphStyle"]["range"]["tabId"] == "t.abc"
        if "updateTextStyle" in r:
            assert r["updateTextStyle"]["range"]["tabId"] == "t.abc"
        if "createParagraphBullets" in r:
            assert r["createParagraphBullets"]["range"]["tabId"] == "t.abc"


def test_end_of_segment_uses_endOfSegmentLocation():
    requests = markdown_to_docs_requests(
        "# Title", end_of_segment=True
    )
    insert = requests[0]["insertText"]
    assert "endOfSegmentLocation" in insert
    assert "location" not in insert


def test_segment_id_propagates_to_ranges():
    requests = markdown_to_docs_requests(
        "# X", start_index=1, segment_id="seg.1"
    )
    insert = requests[0]["insertText"]
    assert insert["location"]["segmentId"] == "seg.1"
    for r in requests[1:]:
        for key in ("updateParagraphStyle", "createParagraphBullets", "updateTextStyle"):
            if key in r:
                assert r[key]["range"]["segmentId"] == "seg.1"
