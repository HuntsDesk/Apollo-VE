# Fork Changelog — Apollo Feature Port

This fork of [`taylorwilsdon/google_workspace_mcp`](https://github.com/taylorwilsdon/google_workspace_mcp) ports the best features from [`blakesplay/apollo`](https://github.com/blakesplay/apollo) (a TypeScript Google Workspace MCP server) into the Python codebase. The goal was to combine upstream's enterprise-grade architecture (OAuth 2.1, multi-user, stateless mode, 12-service coverage) with Apollo's deeper per-service functionality (especially Slides, Docs markdown, and Drive operations).

## Summary

- **25 new MCP tools** (13 Slides, 4 Sheets, 5 Docs, 3 Drive)
- **Extended 2 existing tools** (`create_doc`, `modify_doc_text`) with native markdown rendering
- **2 new Python modules** (`gslides/slides_helpers.py`, `gdocs/docs_markdown_writer.py`)
- **29 new unit tests** — full suite 646/646 passing

No auth/scope changes. No breaking changes to existing tool signatures (only added new optional parameters).

## New Tools by Service

### Google Slides (13 new tools)

Upstream had 5 Slides tools (`create_presentation`, `get_presentation`, `batch_update_presentation`, `get_page`, `get_page_thumbnail`). Apollo exposed 16 Slides actions as rich, single-purpose operations. This fork adds:

| Tool | Tier | Summary |
|---|---|---|
| `format_slides_text` | Extended | Bold/italic/underline/strikethrough/color/font/size on slide elements |
| `format_slides_paragraph` | Extended | Alignment, line spacing, space above/below, bullet presets |
| `style_slides_shape` | Extended | Shape fill, outline color/weight, dash style |
| `set_slides_background` | Extended | Set slide background color |
| `create_slides_text_box` | Extended | Create positioned text box with formatting |
| `create_slides_shape` | Extended | Create rectangle, ellipse, triangle, star, arrow, etc. |
| `get_slides_speaker_notes` | Extended | Read speaker notes from a slide |
| `update_slides_speaker_notes` | Extended | Replace speaker notes on a slide |
| `insert_slides_image` | Extended | Insert image from public URL |
| `delete_slides_element` | Extended | Delete a slide or any page element |
| `replace_slides_text` | Extended | Find-and-replace across a presentation |
| `duplicate_slide` | Extended | Clone a slide; returns new object ID |
| `reorder_slides` | Extended | Move slides to new position |

All tools are thin wrappers around the Slides `batchUpdate` endpoint and share a helper module (`gslides/slides_helpers.py`) providing color parsing, EMU positioning, text-range builders, and notes-shape discovery.

### Google Docs (5 new tools + 2 enhancements)

| Tool | Tier | Summary |
|---|---|---|
| `insert_doc_markdown` | Extended | Insert markdown with native formatting; supports `tab_id`, `segment_id`, `end_of_segment` |
| `insert_doc_link` | Extended | Insert clickable linked text at an index (tab-aware) |
| `insert_doc_person_chip` | Complete | Insert @mention person smart chip by email |
| `insert_doc_file_chip` | Complete | Insert Drive file smart chip from URL |
| `get_doc_smart_chips` | Complete | Extract all person and rich-link chips from a document |

**`create_doc`** gains `format_as_markdown: bool = False`. When true, `content` is parsed as markdown (headings, bold/italic, bullets, numbered lists) and inserted with native Docs formatting instead of plain text.

**`modify_doc_text`** gains `format_as_markdown: bool = False`. When true, `text` is rendered as native markdown for both insertion and range-replacement, and supports `tab_id`/`segment_id`/`end_of_segment` targeting. Mutually exclusive with explicit formatting parameters (bold/italic/font/color/etc.) — markdown provides its own formatting.

A new pure-Python module `gdocs/docs_markdown_writer.py` handles markdown parsing and generates the necessary `insertText` + `updateParagraphStyle` + `createParagraphBullets` + `updateTextStyle` batchUpdate requests with correct cumulative indexing.

Markdown supported:
- `# H1`, `## H2`, `### H3`
- `**bold**`
- `*italic*`
- `- bullets`
- `1. numbered`

### Google Sheets (4 new tools)

| Tool | Tier | Summary |
|---|---|---|
| `add_sheet_data_validation` | Complete | ONE_OF_LIST, NUMBER_BETWEEN/GREATER/LESS, TEXT_CONTAINS, DATE_*, CUSTOM_FORMULA, BOOLEAN |
| `add_sheet_named_range` | Complete | Create a named range for use in formulas |
| `protect_sheet_range` | Complete | Protect a range with editor whitelist and strict/warning modes |
| `manage_sheet_tabs` | Complete | Rename/delete/duplicate sheet tabs (single action-based tool) |

`manage_sheet_tabs` follows upstream's `manage_event` / `manage_contact` convention — a single tool with an `action` parameter for CRUD variants on the same entity.

### Google Drive (3 new tools)

| Tool | Tier | Summary |
|---|---|---|
| `copy_drive_folder` | Complete | Recursively copy a folder tree (folders + files). Sequential to respect rate limits. Returns counts and per-file errors. |
| `get_drive_revisions` | Complete | List a file's revision history (ID, modified time, user, size). |
| `restore_drive_revision` | Complete | Restore a binary file to a prior revision by downloading + re-uploading. Google-native files (Docs/Sheets/Slides) don't support raw-content revisions — for those, use the Docs UI. |

## Files Changed

**Created:**
- `gslides/slides_helpers.py` — Slides utilities (color parsing, EMU builders, text ranges, notes discovery)
- `gdocs/docs_markdown_writer.py` — Markdown → Docs batchUpdate request builder
- `tests/gslides/__init__.py`, `tests/gslides/test_slides_helpers.py`
- `tests/gdocs/test_docs_markdown_writer.py`

**Modified:**
- `gslides/slides_tools.py` — +13 tools
- `gdocs/docs_tools.py` — +5 tools, +`format_as_markdown` on `create_doc` and `modify_doc_text`
- `gsheets/sheets_tools.py` — +4 tools
- `gdrive/drive_tools.py` — +3 tools, +`_list_folder_children` and `_copy_folder_tree` helpers
- `core/tool_tiers.yaml` — +25 tool registrations
- `tests/gdocs/golden/docs_tool_schemas.json` — regenerated to reflect new `format_as_markdown` parameter

## Design Decisions

1. **New Slides tools are standalone**, not consolidated behind `batch_update_presentation`. This matches upstream's one-tool-per-operation pattern and improves LLM discoverability.

2. **Sheets tab management is a single action-based tool** (`manage_sheet_tabs`) rather than three separate tools, matching upstream's `manage_event`, `manage_contact`, `manage_task` conventions.

3. **Markdown conversion is opt-in** via `format_as_markdown=False` default. Auto-detection is fragile (plain text containing `#` or `*` gets misformatted), so we require an explicit flag.

4. **`format_as_markdown` is mutually exclusive with explicit formatting parameters** in `modify_doc_text`. Combining them is semantically ambiguous (does `**bold**` become bold+color:red or just red?). Clean rejection at the boundary.

5. **No changes to authentication, scopes, or the tier system.** All new tools fit cleanly into existing `docs`/`docs_readonly`/`sheets`/`sheets_write`/`drive`/`drive_read`/`slides`/`slides_read` scopes. New Slides tools go in the `extended` tier (they simplify the existing complete-tier `batch_update_presentation`); new Docs/Sheets/Drive tools go in `complete` as power-user features (with `insert_doc_markdown` and `insert_doc_link` in `extended` for their high utility).

6. **Helpers live in separate modules** (`slides_helpers.py`, `docs_markdown_writer.py`) for testability as pure functions with no Google API dependency.

## Testing

- **646/646 tests passing** (617 upstream + 29 new)
- Pure-logic unit tests for `slides_helpers` and `docs_markdown_writer` (no mocks needed)
- `tests/gdocs/golden/docs_tool_schemas.json` regenerated after adding the `format_as_markdown` parameter to `modify_doc_text`
- Server starts cleanly with all new tools registered via `@server.tool()` decorators

## Known Limitations

1. **Drive revision restore** only works for binary files (PDF, DOCX, images). Google-native formats (Docs, Sheets, Slides) don't expose raw revision content via the API; use Google's built-in Version History UI for those.

2. **Speaker notes shape discovery** falls back to scanning `notesPage.pageElements` if `slideProperties.notesObjectId` isn't set — robust for standard slide layouts but may not cover all custom layouts.

3. **Recursive folder copy is sequential**, not parallel, to avoid Drive API rate limits. Large folder trees may take time; per-file errors are collected and reported rather than aborting the whole operation.

4. **Smart chip insertion** relies on Google Docs' auto-conversion of `mailto:` and Drive URL links into chips — there's no dedicated `insertPerson` request in the public batchUpdate API for most cases.
