# CLAUDE.md

## What is this

A Python TUI for reading SillyTavern JSONL chat exports, built with [Textual](https://textual.textualize.io/). Dev dependencies managed with `uv`.

## Project structure

```
viewer.py              — thin entry-point shim (delegates to viewer/)
viewer/
  __init__.py          — re-exports parse_chat, _is_gpg_file for backward compat
  __main__.py          — argparse + CLI entry point
  models.py            — data model: Swipe, Message, Chat, RenderedLine
  parser.py            — JSONL parsing, GPG decryption, load_chat
  render.py            — pre-render messages into flat RenderedLine lists (legacy, used by state.py)
  colors.py            — color pair constants (style identifiers used by render.py)
  state.py             — ViewerState dataclass + scroll/search helper functions
  app.py               — Textual App: widgets, modal screens, key dispatch
tests/
  test_viewer.py       — integration tests using Textual pilot (~15s)
  test_state.py        — unit tests for ViewerState and scroll/search helpers
  test_render.py       — unit tests for rendering functions
  fixture.jsonl        — 5-message test fixture with swipes, reasoning, and metadata
```

Framework-agnostic modules: `models.py`, `parser.py`, `render.py`, `state.py`, `colors.py`. Textual-specific: `app.py`.

## Running the app

```
uv sync
uv run python viewer.py path/to/chat.jsonl
uv run python -m viewer path/to/chat.jsonl
```

## Running tests

```
uv sync
uv run pytest
```

Integration tests use Textual's async pilot framework (~15s). Unit tests for state and render run in ~0.03s.

## Key architecture decisions

- Each message is a `MessageWidget` (Textual `Static`) inside a `VerticalScroll` container. Textual handles scrolling and viewport management.
- Messages render themselves as Rich `Text` objects with styled spans. Text is wrapped manually via `textwrap.wrap()` so every line gets the gutter prefix. Search highlighting uses Rich's `highlight_words`.
- A `StickyHeader` widget appears below the title bar when the current message's header scrolls off-screen, showing its metadata (name, model, tokens, time).
- Modal screens (`SearchScreen`, `GotoScreen`, `HelpScreen`) use Textual's `ModalScreen` with `Input` widgets.
- All key handling goes through `on_key()` with separate dispatch for normal mode and search mode, sharing scroll logic via `_handle_scroll_key`.
- The `▌` cursor marker is rendered in the message content text, matching the original curses UX. Cursor follows scroll — when the selected message leaves the viewport, it snaps to the nearest visible message.
- `render.py` and `state.py` are preserved from the curses era — `find_search_matches` from state.py is used by the Textual app.
