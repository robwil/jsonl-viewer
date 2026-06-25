# CLAUDE.md

## What is this

A Python curses TUI for reading SillyTavern JSONL chat exports. No runtime dependencies beyond the stdlib. Dev dependencies managed with `uv`.

## Project structure

```
viewer.py              — thin entry-point shim (delegates to viewer/)
viewer/
  __init__.py          — re-exports parse_chat, _is_gpg_file for backward compat
  __main__.py          — argparse + CLI entry point
  models.py            — data model: Swipe, Message, Chat, RenderedLine
  parser.py            — JSONL parsing, GPG decryption, load_chat
  render.py            — pre-render messages into flat RenderedLine lists
  colors.py            — curses color pair constants + init_colors
  draw.py              — curses drawing: title bar, sticky header, content lines, search highlights
  dialogs.py           — modal dialogs: goto, search, help overlay
  state.py             — ViewerState dataclass + scroll/search helper functions
  app.py               — main loop, layout calculation, key dispatch
tests/
  test_viewer.py       — integration tests using pyte + pexpect (PTY-based, ~60s)
  test_state.py        — unit tests for ViewerState and scroll/search helpers
  test_render.py       — unit tests for rendering functions
  fixture.jsonl        — 5-message test fixture with swipes, reasoning, and metadata
```

Curses is isolated to `draw.py`, `dialogs.py`, `colors.py`, and `app.py`. The other modules (`models.py`, `parser.py`, `render.py`, `state.py`) are framework-agnostic.

## Running the app

```
python3 viewer.py path/to/chat.jsonl
python3 -m viewer path/to/chat.jsonl
```

## Running tests

```
uv sync
uv run pytest
```

PTY integration tests spawn the viewer in a real pty at a fixed terminal size, send keystrokes, and assert on the pyte-emulated screen buffer (~60s). Unit tests for state and render run in ~0.03s.

## Key architecture decisions

- Messages are pre-rendered into a flat list of `RenderedLine` objects, each tagged with `msg_idx`. The main loop only draws the visible viewport slice.
- `ViewerState` holds all mutable state (cursor, scroll, search, expanded reasoning) with action methods that manage the `needs_rerender`/`scroll_to_cursor` flags.
- The cursor marker (`▌`) is baked into the rendered lines, so changing `cursor_msg` requires a full re-render.
- `curses.set_escdelay(25)` is set so Esc is responsive and doesn't conflict with arrow key escape sequences.
- Search mode is a separate key handler that shares scroll logic with normal mode via `_handle_scroll_key`.
