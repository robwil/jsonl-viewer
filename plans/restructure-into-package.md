# Restructure viewer.py into a multi-file package

## Context

`viewer.py` is a 913-line single-file TUI that works well but has grown organically. Key problems from the audit:

1. **`main()` is 260 lines** (580–838) — conflates state init, viewport geometry, drawing, and two parallel input dispatch trees (search mode + normal mode)
2. **Duplicated scroll keybindings** — lines 729–736 (search mode) copy lines 745–752 (normal mode)
3. **Duplicated dialog boilerplate** — `_goto_dialog` and `_search_dialog` share ~80% structure
4. **10+ bare local state variables** in main() with flag-based deferred actions (`needs_rerender`, `scroll_to_cursor`, `scroll_to_search`) forming an implicit state machine
5. **Five pure functions untested** — `render_messages`, `_build_header_text`, `_cursor_after_scroll`, `_scroll_to_msg`, `_find_search_matches` only exercised via slow PTY tests
6. **Scroll helpers defined after `main()`** (lines 840–885) — breaks reading flow

The existing test suite is almost entirely black-box (PTY + pyte), with only `parse_chat` and `_is_gpg_file` imported directly — so we can refactor internals freely.

## Approach

### 1. Extract `ViewerState` dataclass (biggest win)

All the bare locals in `main()` become fields on a state object:

```python
@dataclass
class ViewerState:
    chat: Chat
    messages: list[Message]
    cursor_msg: int = 0
    scroll_pos: int = 0
    expanded_reasoning: set[int] = field(default_factory=set)
    rendered: list[RenderedLine] = field(default_factory=list)
    line_to_msg: list[int] = field(default_factory=list)
    needs_rerender: bool = True
    needs_clear: bool = True
    scroll_to_cursor: bool = False
    scroll_to_search: str | None = None
    # Search
    search_mode: bool = False
    search_query: str = ""
    search_matches: list[int] = field(default_factory=list)
    search_idx: int = 0
```

Then add methods for the actions that currently repeat:
- `rerender(width)` — rebuild rendered lines
- `scroll_by(delta, max_scroll)` — clamp scroll_pos
- `move_cursor(target)` — set cursor + trigger rerender + scroll
- `next_search_match(direction)` — advance search_idx, move cursor
- `toggle_swipe(direction)` — cycle active_swipe on current message
- `toggle_reasoning()` — expand/collapse reasoning for current message

This eliminates the duplicated `needs_rerender = True; scroll_to_cursor = True` patterns that appear ~8 times.

### 2. Split `main()` into render loop + input dispatch

The 260-line `main()` becomes three pieces:

- **`_update_layout(state, height, width)`** — the scroll/sticky-header/viewport calculation block (lines 606–640). Pure function of state + terminal size, returns layout info.
- **`_draw_frame(stdscr, state, layout)`** — all the `stdscr.addstr` calls (lines 642–698). Takes state + layout, draws everything.
- **`_handle_key(state, key, stdscr, height, width)`** — the if/elif chain (lines 700–838). Mutates state, returns a sentinel to break the loop on quit.

`main()` shrinks to:
```python
def main(stdscr, chat):
    _init_curses(stdscr)
    state = ViewerState(chat=chat, messages=chat.messages)
    while True:
        height, width = stdscr.getmaxyx()
        layout = _update_layout(state, height, width)
        _draw_frame(stdscr, state, layout)
        key = stdscr.getch()
        if _handle_key(state, key, stdscr, height, width) == "quit":
            break
```

### 3. Deduplicate search-mode vs normal-mode scroll keys

Lines 729–738 (search mode scroll) duplicate lines 743–752 (normal mode scroll). Extract a `_handle_scroll_key(state, key, viewable, max_scroll, line_to_msg, total)` helper that both modes call.

### 4. Deduplicate dialog boilerplate

`_goto_dialog` and `_search_dialog` share ~80% structure (box drawing, cursor positioning, key loop). Extract a generic `_input_dialog(stdscr, height, width, prompt, char_filter)` that both call, passing only the prompt text and a character acceptance function (digits-only vs printable).

### 5. Split into modules (file organization)

Create a `viewer/` package:

```
viewer/
  __init__.py          # re-exports parse_chat, _is_gpg_file for backward compat
  __main__.py          # argparse + entry point (~30 lines)
  models.py            # Swipe, Message, Chat, RenderedLine dataclasses (~50 lines)
  parser.py            # parse_chat, load_chat, GPG helpers (~100 lines)
  render.py            # render_messages, _build_header_text, _name_color (~80 lines)
  draw.py              # curses drawing: title bar, sticky header, highlights, help bar (~130 lines)
  dialogs.py           # _input_dialog, goto_dialog, search_dialog, help_overlay (~100 lines)
  state.py             # ViewerState class with action methods (~80 lines)
  app.py               # main loop, _update_layout, _handle_key (~150 lines)
  colors.py            # color pair constants + init_colors (~30 lines)
```

Keep `viewer.py` as a thin shim for backward compatibility (tests spawn `python3 viewer.py`):
```python
#!/usr/bin/env python3
from viewer.__main__ import main_cli
if __name__ == "__main__":
    main_cli()
```

The `viewer/__init__.py` re-exports `parse_chat` and `_is_gpg_file` so the 2 direct-import tests don't break.

### 6. Update tests

- The PTY tests just need the spawn command to still work (`python3 viewer.py fixture.jsonl`), which the shim ensures.
- The 2 unit tests importing `from viewer import parse_chat` / `_is_gpg_file` continue to work via the shim re-exports.
- Add new unit tests for `ViewerState` methods (cursor movement, search navigation, swipe cycling) — these are fast, no PTY needed.

## Files to create/modify

- **Create**: `viewer/` package — `__init__.py`, `__main__.py`, `models.py`, `parser.py`, `render.py`, `draw.py`, `dialogs.py`, `state.py`, `app.py`, `colors.py`
- **Modify**: `viewer.py` → thin shim (~5 lines)
- **Modify**: `CLAUDE.md` → update project structure section
- **Add tests**: `tests/test_state.py` for ViewerState unit tests (cursor movement, search nav, swipe cycling, scroll helpers)
- **Add tests**: `tests/test_render.py` for pure rendering functions (`render_messages`, `_build_header_text`)

## Design for future Textual migration

The module split is deliberately drawn so curses is isolated to 3 files (`draw.py`, `dialogs.py`, `colors.py`) while everything else is framework-agnostic:

- **`models.py`** — pure dataclasses, no curses imports
- **`parser.py`** — file I/O + JSON parsing, no curses
- **`render.py`** — produces `RenderedLine` objects (plain data), no curses
- **`state.py`** — ViewerState with action methods, no curses

A future Textual rewrite would replace `draw.py`, `dialogs.py`, `colors.py`, and `app.py` while keeping models/parser/render/state unchanged. The `RenderedLine` abstraction becomes the bridge: Textual widgets consume the same pre-rendered line data that curses drawing does today.

## Verification

1. `uv run pytest` — all existing PTY tests pass unchanged
2. `python3 viewer.py <fixture>` — app still launches and works
3. `python3 -m viewer <fixture>` — also works via `__main__.py`
4. New unit tests for ViewerState and render functions pass
5. Each module can be read and understood in isolation
