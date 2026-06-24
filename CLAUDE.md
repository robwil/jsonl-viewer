# CLAUDE.md

## What is this

A Python curses TUI for reading SillyTavern JSONL chat exports. Single-file app (`viewer.py`) with no runtime dependencies beyond the stdlib. Dev dependencies managed with `uv`.

## Project structure

- `viewer.py` — the entire application (parsing, rendering, input handling)
- `tests/test_viewer.py` — integration tests using pyte (terminal emulator) + pexpect (pty driver)
- `tests/fixture.jsonl` — 5-message test fixture with swipes, reasoning, and metadata

## Running the app

```
python3 viewer.py path/to/chat.jsonl
```

## Running tests

```
uv sync
uv run pytest
```

Tests spawn the viewer in a real pty at a fixed terminal size, send keystrokes, and assert on the pyte-emulated screen buffer. They take ~40s due to pty timing delays.

## Key architecture decisions

- Everything is in one file. The data model (`Chat`, `Message`, `Swipe`) and all rendering/input logic live in `viewer.py`.
- Messages are pre-rendered into a flat list of `RenderedLine` objects, each tagged with `msg_idx`. The main loop only draws the visible viewport slice.
- The cursor marker (`▌`) is baked into the rendered lines, so changing `cursor_msg` requires a full re-render.
- `curses.set_escdelay(25)` is set so Esc is responsive and doesn't conflict with arrow key escape sequences.
- Search mode is a separate input loop that overrides the help bar and n/N bindings.
