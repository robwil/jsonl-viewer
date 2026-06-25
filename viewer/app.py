"""Main application loop for the TUI viewer."""

import curses
from dataclasses import dataclass

from .colors import init_colors
from .dialogs import draw_help_overlay, goto_dialog, search_dialog
from .draw import draw_content_line, draw_help_bar, draw_search_bar, draw_sticky_header, draw_title_bar
from .models import Chat
from .state import (
    ViewerState,
    cursor_after_scroll,
    is_header_visible,
    scroll_to_match,
    scroll_to_msg,
)


@dataclass
class Layout:
    show_sticky: bool
    header_rows: int
    viewable: int
    max_scroll: int
    total: int


def _init_curses(stdscr):
    curses.curs_set(0)
    init_colors()
    curses.set_escdelay(25)
    curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
    stdscr.timeout(-1)
    stdscr.keypad(True)


def _update_layout(state: ViewerState, height: int, width: int) -> Layout:
    """Calculate viewport geometry from current state."""
    if state.needs_rerender:
        state.rerender(width)

    show_sticky = not is_header_visible(
        state.cursor_msg, state.scroll_pos, height - 2, state.rendered)
    header_rows = 2 if show_sticky else 1
    viewable = height - 1 - header_rows
    total = len(state.rendered)
    max_scroll = max(0, total - viewable)

    if state.scroll_to_cursor:
        if state.scroll_to_search:
            state.scroll_pos = scroll_to_match(
                state.cursor_msg, state.scroll_to_search,
                state.rendered, state.line_to_msg, viewable, max_scroll)
            state.scroll_to_search = None
        else:
            state.scroll_pos = scroll_to_msg(
                state.cursor_msg, state.rendered, state.line_to_msg,
                state.scroll_pos, viewable, max_scroll)
        state.scroll_to_cursor = False
        # Recheck sticky after scroll adjustment
        show_sticky = not is_header_visible(
            state.cursor_msg, state.scroll_pos, viewable, state.rendered)
        header_rows = 2 if show_sticky else 1
        viewable = height - 1 - header_rows
        max_scroll = max(0, total - viewable)

    state.scroll_pos = max(0, min(state.scroll_pos, max_scroll))

    return Layout(show_sticky=show_sticky, header_rows=header_rows,
                  viewable=viewable, max_scroll=max_scroll, total=total)


def _draw_frame(stdscr, state: ViewerState, layout: Layout, height: int, width: int):
    """Draw the complete frame."""
    if state.needs_clear:
        stdscr.clear()
        state.needs_clear = False
    else:
        stdscr.erase()

    draw_title_bar(stdscr, 0, width, state.chat, state.cursor_msg, len(state.messages))

    if layout.show_sticky and 0 <= state.cursor_msg < len(state.messages):
        draw_sticky_header(stdscr, 1, width,
                           state.messages[state.cursor_msg], state.cursor_msg + 1)

    for i in range(layout.viewable):
        line_idx = state.scroll_pos + i
        if line_idx >= layout.total:
            break
        screen_row = layout.header_rows + i
        draw_content_line(stdscr, screen_row, width,
                          state.rendered[line_idx],
                          state.search_mode, state.search_query)

    if state.search_mode:
        match_pos = (state.search_matches.index(state.cursor_msg) + 1
                     if state.cursor_msg in state.search_matches else 0)
        draw_search_bar(stdscr, height, width, state.search_query,
                        match_pos, len(state.search_matches))
    else:
        draw_help_bar(stdscr, height, width)

    stdscr.refresh()


def _handle_scroll_key(state: ViewerState, key: int, layout: Layout) -> bool:
    """Handle scroll/page keys common to both modes. Returns True if handled."""
    if key in (curses.KEY_DOWN, ord("j")):
        state.scroll_pos = min(state.scroll_pos + 1, layout.max_scroll)
    elif key in (curses.KEY_UP, ord("k")):
        state.scroll_pos = max(state.scroll_pos - 1, 0)
    elif key in (curses.KEY_NPAGE, ord(" ")):
        state.scroll_pos = min(state.scroll_pos + layout.viewable, layout.max_scroll)
    elif key == curses.KEY_PPAGE:
        state.scroll_pos = max(state.scroll_pos - layout.viewable, 0)
    else:
        return False
    return True


def _handle_search_key(state: ViewerState, key: int,
                       stdscr, height: int, width: int, layout: Layout) -> str | None:
    """Handle keys in search mode. Returns 'quit' to exit app."""
    if key == 27:
        state.exit_search()
    elif key == ord("n"):
        state.next_search_match(1)
    elif key in (ord("N"), ord("p")):
        state.next_search_match(-1)
    elif key == ord("/"):
        query = search_dialog(stdscr, height, width)
        state.needs_clear = True
        if query:
            state.start_search(query)
    elif key == ord("q"):
        return "quit"
    else:
        _handle_scroll_key(state, key, layout)
    return None


def _handle_normal_key(state: ViewerState, key: int,
                       stdscr, height: int, width: int, layout: Layout) -> str | None:
    """Handle keys in normal mode. Returns 'quit' to exit app."""
    if key == ord("q") or key == 27:
        return "quit"

    if _handle_scroll_key(state, key, layout):
        new_cursor = cursor_after_scroll(
            state.cursor_msg, state.scroll_pos, layout.viewable,
            state.line_to_msg, layout.total)
        if new_cursor != state.cursor_msg:
            state.cursor_msg = new_cursor
            state.needs_rerender = True
        return None

    if key in (ord("g"), ord("G")):
        target = goto_dialog(stdscr, height, width, len(state.messages))
        state.needs_clear = True
        if target is not None:
            state.move_cursor(target)
    elif key == ord("n"):
        state.move_cursor(state.cursor_msg + 1)
    elif key in (ord("p"), ord("N")):
        state.move_cursor(state.cursor_msg - 1)
    elif key == ord("r"):
        state.toggle_reasoning()
    elif key in (curses.KEY_LEFT, ord("h")):
        state.toggle_swipe(-1)
    elif key in (curses.KEY_RIGHT, ord("l")):
        state.toggle_swipe(1)
    elif key == ord("?"):
        draw_help_overlay(stdscr, height, width)
        state.needs_clear = True
    elif key == ord("/"):
        query = search_dialog(stdscr, height, width)
        state.needs_clear = True
        if query:
            state.start_search(query)
    elif key == curses.KEY_MOUSE:
        _handle_mouse(state, layout)
    elif key == curses.KEY_RESIZE:
        state.needs_rerender = True

    return None


def _handle_mouse(state: ViewerState, layout: Layout):
    """Handle mouse events."""
    try:
        _, mx, my, _, bstate = curses.getmouse()
        scroll_lines = 3
        # macOS reports scroll-down as REPORT_MOUSE_POSITION (0x8000000)
        SCROLL_DOWN = getattr(curses, "BUTTON5_PRESSED", 0) | curses.REPORT_MOUSE_POSITION
        if bstate & curses.BUTTON4_PRESSED:
            state.scroll_pos = max(state.scroll_pos - scroll_lines, 0)
            new_cursor = cursor_after_scroll(
                state.cursor_msg, state.scroll_pos, layout.viewable,
                state.line_to_msg, layout.total)
            if new_cursor != state.cursor_msg:
                state.cursor_msg = new_cursor
                state.needs_rerender = True
        elif bstate & SCROLL_DOWN:
            state.scroll_pos = min(state.scroll_pos + scroll_lines, layout.max_scroll)
            new_cursor = cursor_after_scroll(
                state.cursor_msg, state.scroll_pos, layout.viewable,
                state.line_to_msg, layout.total)
            if new_cursor != state.cursor_msg:
                state.cursor_msg = new_cursor
                state.needs_rerender = True
        elif bstate & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
            content_row = my - layout.header_rows
            line_idx = state.scroll_pos + content_row
            if 0 <= content_row < layout.viewable and 0 <= line_idx < len(state.line_to_msg):
                clicked_msg = state.line_to_msg[line_idx]
                if clicked_msg != state.cursor_msg:
                    state.cursor_msg = clicked_msg
                    state.needs_rerender = True
    except curses.error:
        pass


def main(stdscr, chat: Chat):
    _init_curses(stdscr)
    state = ViewerState(chat=chat, messages=chat.messages)

    while True:
        height, width = stdscr.getmaxyx()
        layout = _update_layout(state, height, width)
        _draw_frame(stdscr, state, layout, height, width)
        key = stdscr.getch()

        if state.search_mode:
            result = _handle_search_key(state, key, stdscr, height, width, layout)
        else:
            result = _handle_normal_key(state, key, stdscr, height, width, layout)

        if result == "quit":
            break
