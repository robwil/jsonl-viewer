"""Modal dialog boxes for the viewer."""

import curses
from typing import Callable

from .colors import CP_HELP_BAR


HELP_LINES = [
    "Keybindings",
    "",
    "  ↑ / k          Scroll up one line",
    "  ↓ / j          Scroll down one line",
    "  PgUp            Scroll up one page",
    "  PgDn / Space    Scroll down one page",
    "  g / G           Go to message by ID",
    "",
    "  n               Next message",
    "  N / p           Previous message",
    "",
    "  ← / h           Previous swipe",
    "  → / l           Next swipe",
    "",
    "  r               Toggle reasoning",
    "",
    "  /               Search message text",
    "                  n/N to navigate results",
    "",
    "  q / Esc         Quit",
    "  ?               This help",
]


def _input_dialog(stdscr, height: int, width: int, prompt: str,
                  char_filter: Callable[[int], bool]) -> str | None:
    """Generic input dialog. Returns input string or None if cancelled.

    char_filter receives a key code and returns True if the character should
    be accepted into the input buffer.
    """
    box_w = min(max(len(prompt) + 12, 60), width - 4)
    box_h = 5
    start_y = (height - box_h) // 2
    start_x = (width - box_w) // 2
    input_buf = ""

    while True:
        for row in range(box_h):
            y = start_y + row
            if row == 0:
                line = "┌" + "─" * (box_w - 2) + "┐"
            elif row == box_h - 1:
                line = "└" + "─" * (box_w - 2) + "┘"
            elif row == 2:
                inner = f"{prompt}{input_buf}"
                inner = inner[:box_w - 4]
                line = "│ " + inner.ljust(box_w - 4) + " │"
            else:
                line = "│" + " " * (box_w - 2) + "│"
            try:
                stdscr.addnstr(y, start_x, line, box_w,
                               curses.color_pair(CP_HELP_BAR) | curses.A_BOLD)
            except curses.error:
                pass

        cursor_x = start_x + 2 + len(prompt) + len(input_buf)
        if cursor_x < start_x + box_w - 2:
            try:
                curses.curs_set(1)
                stdscr.move(start_y + 2, cursor_x)
            except curses.error:
                pass

        stdscr.refresh()
        k = stdscr.getch()

        if k == 27:
            curses.curs_set(0)
            return None
        elif k in (ord("\n"), curses.KEY_ENTER):
            curses.curs_set(0)
            return input_buf if input_buf else None
        elif k in (curses.KEY_BACKSPACE, 127, 8):
            input_buf = input_buf[:-1]
        elif char_filter(k):
            input_buf += chr(k)


def goto_dialog(stdscr, height: int, width: int, total_msgs: int) -> int | None:
    """Show a goto dialog, return 0-based message index or None if cancelled."""
    prompt = f"Go to message (1-{total_msgs}): "
    result = _input_dialog(
        stdscr, height, width, prompt,
        char_filter=lambda k: 0 <= k <= 255 and chr(k).isdigit(),
    )
    if result is not None:
        try:
            num = int(result)
            if 1 <= num <= total_msgs:
                return num - 1
        except ValueError:
            pass
    return None


def search_dialog(stdscr, height: int, width: int) -> str | None:
    """Show a search input dialog, return query or None if cancelled."""
    return _input_dialog(
        stdscr, height, width, "Search: ",
        char_filter=lambda k: 32 <= k <= 126,
    )


def draw_help_overlay(stdscr, height, width):
    box_w = min(max(len(l) for l in HELP_LINES) + 6, width - 4)
    box_h = min(len(HELP_LINES) + 4, height - 2)
    start_y = (height - box_h) // 2
    start_x = (width - box_w) // 2

    for row in range(box_h):
        y = start_y + row
        if y < 0 or y >= height:
            continue
        if row == 0:
            line = "┌" + "─" * (box_w - 2) + "┐"
        elif row == box_h - 1:
            line = "└" + "─" * (box_w - 2) + "┘"
        else:
            content_idx = row - 2
            if 0 <= content_idx < len(HELP_LINES):
                inner = HELP_LINES[content_idx]
            else:
                inner = ""
            inner = inner[:box_w - 4]
            line = "│ " + inner.ljust(box_w - 4) + " │"
        try:
            stdscr.addnstr(y, start_x, line, box_w,
                           curses.color_pair(CP_HELP_BAR) | curses.A_BOLD)
        except curses.error:
            pass

    stdscr.refresh()
    while True:
        k = stdscr.getch()
        if k in (ord("?"), ord("q"), 27, ord("\n")):
            break
